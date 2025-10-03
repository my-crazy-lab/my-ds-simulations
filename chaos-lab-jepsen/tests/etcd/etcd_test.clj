(ns etcd-test
  "Jepsen test for etcd distributed key-value store.
   Tests linearizability, partition tolerance, and consistency guarantees."
  (:require [clojure.tools.logging :refer :all]
            [clojure.string :as str]
            [jepsen [checker :as checker]
                    [cli :as cli]
                    [client :as client]
                    [control :as c]
                    [db :as db]
                    [generator :as gen]
                    [nemesis :as nemesis]
                    [tests :as tests]]
            [jepsen.checker.timeline :as timeline]
            [jepsen.control.util :as cu]
            [jepsen.os.debian :as debian]
            [knossos.model :as model]
            [verschlimmbesserung.core :as v])
  (:import (knossos.model Model)))

(def etcd-endpoints
  "etcd cluster endpoints"
  ["http://etcd-1:2379" "http://etcd-2:2379" "http://etcd-3:2379"])

(defn etcd-client
  "Creates an etcd client for the given node"
  [node]
  (let [endpoint (str "http://" node ":2379")]
    {:endpoint endpoint
     :timeout 5000}))

(defrecord EtcdClient [conn]
  client/Client
  (open! [this test node]
    (assoc this :conn (etcd-client node)))

  (setup! [this test])

  (invoke! [this test op]
    (let [{:keys [f key value]} op]
      (try
        (case f
          :read (let [result (etcd-get (:conn this) key)]
                  (assoc op :type :ok :value result))
          
          :write (do (etcd-put (:conn this) key value)
                     (assoc op :type :ok))
          
          :cas (let [old-value (:value op)
                     new-value (:new-value op)
                     success? (etcd-cas (:conn this) key old-value new-value)]
                 (assoc op :type (if success? :ok :fail))))
        
        (catch Exception e
          (assoc op :type :info :error (.getMessage e))))))

  (teardown! [this test])

  (close! [_ test]))

(defn etcd-get
  "Get value from etcd"
  [client key]
  (try
    (let [cmd (format "curl -s %s/v2/keys/%s" (:endpoint client) key)
          result (c/exec :bash :-c cmd)]
      (when-let [parsed (parse-etcd-response result)]
        (:value parsed)))
    (catch Exception e
      (warn "etcd-get failed:" (.getMessage e))
      nil)))

(defn etcd-put
  "Put value to etcd"
  [client key value]
  (let [cmd (format "curl -s -X PUT %s/v2/keys/%s -d value=%s" 
                    (:endpoint client) key value)]
    (c/exec :bash :-c cmd)))

(defn etcd-cas
  "Compare-and-swap operation on etcd"
  [client key old-value new-value]
  (try
    (let [cmd (format "curl -s -X PUT %s/v2/keys/%s -d value=%s -d prevValue=%s"
                      (:endpoint client) key new-value old-value)
          result (c/exec :bash :-c cmd)]
      (not (str/includes? result "error")))
    (catch Exception e
      false)))

(defn parse-etcd-response
  "Parse etcd JSON response"
  [response]
  (try
    (let [parsed (json/read-str response :key-fn keyword)]
      (get-in parsed [:node :value]))
    (catch Exception e
      nil)))

(defn etcd-db
  "etcd database setup"
  []
  (reify db/DB
    (setup! [_ test node]
      (info node "Setting up etcd")
      (c/su
        ; etcd is already running in containers
        ; Just verify connectivity
        (c/exec :curl :-f (str "http://" node ":2379/health"))))

    (teardown! [_ test node]
      (info node "Tearing down etcd"))

    db/LogFiles
    (log-files [_ test node]
      ["/var/log/etcd.log"])))

(defn register-workload
  "A simple register workload for linearizability testing"
  [opts]
  {:client    (->EtcdClient nil)
   :checker   (checker/compose
                {:perf     (checker/perf)
                 :timeline (timeline/html)
                 :linear   (checker/linearizable
                             {:model     (model/register)
                              :algorithm :linear})})
   :generator (gen/mix [gen/r gen/w gen/cas])
   :final-generator (gen/once gen/r)})

(defn bank-workload
  "Bank account transfer workload for testing consistency"
  [opts]
  (let [accounts (range (:accounts opts 8))
        initial-balance (:initial-balance opts 100)]
    {:client    (->EtcdClient nil)
     :checker   (checker/compose
                  {:perf     (checker/perf)
                   :timeline (timeline/html)
                   :bank     (bank-checker accounts initial-balance)})
     :generator (gen/mix [(gen/reserve 5 (bank-read accounts))
                          (bank-transfer accounts (:max-transfer opts 50))])
     :final-generator (gen/once (bank-read accounts))}))

(defn bank-checker
  "Checker for bank account invariants"
  [accounts initial-balance]
  (reify checker/Checker
    (check [this test history opts]
      (let [total-initial (* (count accounts) initial-balance)
            final-ops (filter #(= :read (:f %)) 
                             (filter #(= :ok (:type %)) history))
            final-balances (map :value final-ops)
            total-final (reduce + final-balances)]
        {:valid? (= total-initial total-final)
         :total-initial total-initial
         :total-final total-final
         :difference (- total-final total-initial)}))))

(defn bank-read
  "Generate bank account read operations"
  [accounts]
  (gen/mix (map (fn [account]
                  {:f :read :key (str "account-" account)})
                accounts)))

(defn bank-transfer
  "Generate bank account transfer operations"
  [accounts max-amount]
  (gen/mix
    (repeatedly
      (fn []
        (let [from (rand-nth accounts)
              to (rand-nth (remove #{from} accounts))
              amount (inc (rand-int max-amount))]
          {:f :transfer 
           :from (str "account-" from)
           :to (str "account-" to)
           :amount amount})))))

(defn set-workload
  "Set workload for testing set consistency"
  [opts]
  {:client    (->EtcdClient nil)
   :checker   (checker/compose
                {:perf     (checker/perf)
                 :timeline (timeline/html)
                 :set      (checker/set)})
   :generator (gen/mix [set-add set-read])
   :final-generator (gen/once set-read)})

(def set-add
  "Add element to set"
  (gen/map (fn [_] {:f :add :value (rand-int 1000)})))

(def set-read
  "Read entire set"
  (gen/map (fn [_] {:f :read})))

(defn partition-nemesis
  "Network partition nemesis"
  [opts]
  (nemesis/partition-random-halves))

(defn kill-nemesis
  "Process kill nemesis"
  [opts]
  (nemesis/partition-random-node))

(defn clock-nemesis
  "Clock skew nemesis"
  [opts]
  (nemesis/clock-scrambler 10000))

(defn mixed-nemesis
  "Mixed failure scenarios"
  [opts]
  (nemesis/compose
    {{:partition-start :partition-start
      :partition-stop  :partition-stop} (partition-nemesis opts)
     {:kill-start      :kill-start
      :kill-stop       :kill-stop}      (kill-nemesis opts)
     {:clock-start     :clock-start
      :clock-stop      :clock-stop}     (clock-nemesis opts)}))

(defn etcd-test
  "Constructs a Jepsen test for etcd"
  [opts]
  (merge tests/noop-test
         opts
         {:name      "etcd"
          :os        debian/os
          :db        (etcd-db)
          :nodes     ["n1" "n2" "n3" "n4" "n5"]
          :nemesis   (mixed-nemesis opts)
          :generator (gen/phases
                       (->> (:workload opts)
                            :generator
                            (gen/stagger 1/10)
                            (gen/nemesis
                              (gen/seq (cycle [(gen/sleep 30)
                                               {:type :info :f :partition-start}
                                               (gen/sleep 30)
                                               {:type :info :f :partition-stop}
                                               (gen/sleep 30)])))
                            (gen/time-limit (:time-limit opts 300)))
                       (gen/nemesis {:type :info :f :partition-stop})
                       (gen/log "Healing cluster")
                       (gen/sleep 10)
                       (:final-generator (:workload opts)))}))

(defn linearizability-test
  "Linearizability test for etcd register"
  [opts]
  (etcd-test (merge opts {:workload (register-workload opts)})))

(defn bank-test
  "Bank account consistency test"
  [opts]
  (etcd-test (merge opts {:workload (bank-workload opts)})))

(defn set-test
  "Set consistency test"
  [opts]
  (etcd-test (merge opts {:workload (set-workload opts)})))

(defn -main
  "Command line entry point"
  [& args]
  (cli/run! (merge (cli/single-test-cmd {:test-fn linearizability-test})
                   (cli/test-all-cmd {:tests-fn (constantly
                                                  {"linearizability" linearizability-test
                                                   "bank"            bank-test
                                                   "set"             set-test})})
                   {:opt-spec [["-w" "--workload NAME" "Workload type"
                                :default "linearizability"
                                :validate [#{"linearizability" "bank" "set"}]]
                               ["-t" "--time-limit SECONDS" "Test duration"
                                :default 300
                                :parse-fn #(Integer/parseInt %)]
                               ["-c" "--concurrency THREADS" "Concurrent operations"
                                :default 10
                                :parse-fn #(Integer/parseInt %)]
                               ["-a" "--accounts COUNT" "Number of bank accounts"
                                :default 8
                                :parse-fn #(Integer/parseInt %)]
                               ["-m" "--max-transfer AMOUNT" "Maximum transfer amount"
                                :default 50
                                :parse-fn #(Integer/parseInt %)]]})
            args))
