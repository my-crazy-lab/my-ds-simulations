package main

import (
	"context"
	"flag"
	"os"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	autoscalingv2 "k8s.io/api/autoscaling/v2"
	corev1 "k8s.io/api/core/v1"
	policyv1 "k8s.io/api/policy/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	_ "k8s.io/client-go/plugin/pkg/client/auth"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	"sigs.k8s.io/controller-runtime/pkg/metrics/server"
	"sigs.k8s.io/controller-runtime/pkg/webhook"

	platformv1 "github.com/platform/operator/api/v1"
	"github.com/platform/operator/controllers"
	//+kubebuilder:scaffold:imports
)

var (
	scheme   = runtime.NewScheme()
	setupLog = ctrl.Log.WithName("setup")
)

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(platformv1.AddToScheme(scheme))
	//+kubebuilder:scaffold:scheme
}

func main() {
	var metricsAddr string
	var enableLeaderElection bool
	var probeAddr string
	var webhookPort int
	var reconcileInterval time.Duration
	var maxConcurrentReconciles int

	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "The address the metric endpoint binds to.")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "The address the probe endpoint binds to.")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false,
		"Enable leader election for controller manager. "+
			"Enabling this will ensure there is only one active controller manager.")
	flag.IntVar(&webhookPort, "webhook-port", 9443, "The port that the webhook server serves at.")
	flag.DurationVar(&reconcileInterval, "reconcile-interval", 30*time.Second, "The interval for reconciliation.")
	flag.IntVar(&maxConcurrentReconciles, "max-concurrent-reconciles", 5, "Maximum number of concurrent reconciles.")

	opts := zap.Options{
		Development: true,
	}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme: scheme,
		Metrics: server.Options{
			BindAddress: metricsAddr,
		},
		WebhookServer: webhook.NewServer(webhook.Options{
			Port: webhookPort,
		}),
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "webapp-operator-leader-election",
	})
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	// Setup WebApp controller
	if err = (&controllers.WebAppReconciler{
		Client:                  mgr.GetClient(),
		Scheme:                  mgr.GetScheme(),
		Recorder:                mgr.GetEventRecorderFor("webapp-controller"),
		ReconcileInterval:       reconcileInterval,
		MaxConcurrentReconciles: maxConcurrentReconciles,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "WebApp")
		os.Exit(1)
	}

	// Setup Database controller
	if err = (&controllers.DatabaseReconciler{
		Client:                  mgr.GetClient(),
		Scheme:                  mgr.GetScheme(),
		Recorder:                mgr.GetEventRecorderFor("database-controller"),
		ReconcileInterval:       reconcileInterval,
		MaxConcurrentReconciles: maxConcurrentReconciles,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Database")
		os.Exit(1)
	}

	// Setup Cache controller
	if err = (&controllers.CacheReconciler{
		Client:                  mgr.GetClient(),
		Scheme:                  mgr.GetScheme(),
		Recorder:                mgr.GetEventRecorderFor("cache-controller"),
		ReconcileInterval:       reconcileInterval,
		MaxConcurrentReconciles: maxConcurrentReconciles,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "Cache")
		os.Exit(1)
	}

	// Setup webhooks
	if err = (&platformv1.WebApp{}).SetupWebhookWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create webhook", "webhook", "WebApp")
		os.Exit(1)
	}

	if err = (&platformv1.Database{}).SetupWebhookWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create webhook", "webhook", "Database")
		os.Exit(1)
	}

	if err = (&platformv1.Cache{}).SetupWebhookWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create webhook", "webhook", "Cache")
		os.Exit(1)
	}

	//+kubebuilder:scaffold:builder

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	// Setup custom metrics
	setupCustomMetrics()

	// Setup leader election callbacks
	setupLeaderElectionCallbacks(mgr)

	setupLog.Info("starting manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

func setupCustomMetrics() {
	// Register custom Prometheus metrics for the operator
	setupLog.Info("setting up custom metrics")

	// These would be defined in a separate metrics package
	// metrics.RegisterOperatorMetrics()
}

func setupLeaderElectionCallbacks(mgr ctrl.Manager) {
	// Setup callbacks for leader election events
	setupLog.Info("setting up leader election callbacks")

	// Add callbacks for when this instance becomes leader or loses leadership
	// This is useful for cleanup operations and ensuring only one instance
	// performs certain operations
}

// WebAppReconciler reconciles a WebApp object
type WebAppReconciler struct {
	client.Client
	Scheme                  *runtime.Scheme
	Recorder                record.EventRecorder
	ReconcileInterval       time.Duration
	MaxConcurrentReconciles int
}

//+kubebuilder:rbac:groups=platform.example.com,resources=webapps,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=platform.example.com,resources=webapps/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=platform.example.com,resources=webapps/finalizers,verbs=update
//+kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=core,resources=services,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=core,resources=configmaps,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=core,resources=secrets,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=networking.k8s.io,resources=ingresses,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=autoscaling,resources=horizontalpodautoscalers,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=policy,resources=poddisruptionbudgets,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=monitoring.coreos.com,resources=servicemonitors,verbs=get;list;watch;create;update;patch;delete

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *WebAppReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := ctrl.LoggerFrom(ctx)

	// Fetch the WebApp instance
	var webapp platformv1.WebApp
	if err := r.Get(ctx, req.NamespacedName, &webapp); err != nil {
		if apierrors.IsNotFound(err) {
			// Request object not found, could have been deleted after reconcile request.
			log.Info("WebApp resource not found. Ignoring since object must be deleted")
			return ctrl.Result{}, nil
		}
		log.Error(err, "Failed to get WebApp")
		return ctrl.Result{}, err
	}

	// Handle deletion
	if webapp.DeletionTimestamp != nil {
		return r.handleDeletion(ctx, &webapp)
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(&webapp, platformv1.WebAppFinalizer) {
		controllerutil.AddFinalizer(&webapp, platformv1.WebAppFinalizer)
		if err := r.Update(ctx, &webapp); err != nil {
			log.Error(err, "Failed to add finalizer")
			return ctrl.Result{}, err
		}
		return ctrl.Result{Requeue: true}, nil
	}

	// Reconcile the desired state
	result, err := r.reconcileWebApp(ctx, &webapp)
	if err != nil {
		// Update status with error
		webapp.Status.Phase = platformv1.WebAppPhaseFailed
		webapp.Status.Message = err.Error()
		if statusErr := r.Status().Update(ctx, &webapp); statusErr != nil {
			log.Error(statusErr, "Failed to update WebApp status")
		}

		// Record event
		r.Recorder.Event(&webapp, corev1.EventTypeWarning, "ReconcileError", err.Error())

		return result, err
	}

	// Update status on success
	if webapp.Status.Phase != platformv1.WebAppPhaseReady {
		webapp.Status.Phase = platformv1.WebAppPhaseReady
		webapp.Status.Message = "WebApp is ready"
		webapp.Status.ObservedGeneration = webapp.Generation

		if err := r.Status().Update(ctx, &webapp); err != nil {
			log.Error(err, "Failed to update WebApp status")
			return ctrl.Result{}, err
		}

		r.Recorder.Event(&webapp, corev1.EventTypeNormal, "Ready", "WebApp is ready")
	}

	// Requeue after the configured interval
	return ctrl.Result{RequeueAfter: r.ReconcileInterval}, nil
}

func (r *WebAppReconciler) reconcileWebApp(ctx context.Context, webapp *platformv1.WebApp) (ctrl.Result, error) {
	log := ctrl.LoggerFrom(ctx)

	// Reconcile Deployment
	if err := r.reconcileDeployment(ctx, webapp); err != nil {
		log.Error(err, "Failed to reconcile Deployment")
		return ctrl.Result{}, err
	}

	// Reconcile Service
	if err := r.reconcileService(ctx, webapp); err != nil {
		log.Error(err, "Failed to reconcile Service")
		return ctrl.Result{}, err
	}

	// Reconcile ConfigMap if specified
	if webapp.Spec.Config != nil {
		if err := r.reconcileConfigMap(ctx, webapp); err != nil {
			log.Error(err, "Failed to reconcile ConfigMap")
			return ctrl.Result{}, err
		}
	}

	// Reconcile HPA if autoscaling is enabled
	if webapp.Spec.Autoscaling != nil && webapp.Spec.Autoscaling.Enabled {
		if err := r.reconcileHPA(ctx, webapp); err != nil {
			log.Error(err, "Failed to reconcile HPA")
			return ctrl.Result{}, err
		}
	}

	// Reconcile PDB if specified
	if webapp.Spec.PodDisruptionBudget != nil {
		if err := r.reconcilePDB(ctx, webapp); err != nil {
			log.Error(err, "Failed to reconcile PDB")
			return ctrl.Result{}, err
		}
	}

	// Reconcile ServiceMonitor if monitoring is enabled
	if webapp.Spec.Monitoring != nil && webapp.Spec.Monitoring.Enabled {
		if err := r.reconcileServiceMonitor(ctx, webapp); err != nil {
			log.Error(err, "Failed to reconcile ServiceMonitor")
			return ctrl.Result{}, err
		}
	}

	// Reconcile Ingress if specified
	if webapp.Spec.Ingress != nil {
		if err := r.reconcileIngress(ctx, webapp); err != nil {
			log.Error(err, "Failed to reconcile Ingress")
			return ctrl.Result{}, err
		}
	}

	return ctrl.Result{}, nil
}

func (r *WebAppReconciler) reconcileDeployment(ctx context.Context, webapp *platformv1.WebApp) error {
	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      webapp.Name,
			Namespace: webapp.Namespace,
		},
	}

	op, err := controllerutil.CreateOrUpdate(ctx, r.Client, deployment, func() error {
		// Set owner reference
		if err := controllerutil.SetControllerReference(webapp, deployment, r.Scheme); err != nil {
			return err
		}

		// Update deployment spec based on WebApp spec
		deployment.Spec = appsv1.DeploymentSpec{
			Replicas: &webapp.Spec.Replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app":     webapp.Name,
					"version": webapp.Spec.Version,
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app":     webapp.Name,
						"version": webapp.Spec.Version,
					},
					Annotations: map[string]string{
						"prometheus.io/scrape": "true",
						"prometheus.io/port":   "8080",
						"prometheus.io/path":   "/metrics",
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  webapp.Name,
							Image: webapp.Spec.Image,
							Ports: []corev1.ContainerPort{
								{
									Name:          "http",
									ContainerPort: 8080,
									Protocol:      corev1.ProtocolTCP,
								},
							},
							Resources: webapp.Spec.Resources,
							Env:       webapp.Spec.Env,
							LivenessProbe: &corev1.Probe{
								ProbeHandler: corev1.ProbeHandler{
									HTTPGet: &corev1.HTTPGetAction{
										Path: "/health",
										Port: intstr.FromString("http"),
									},
								},
								InitialDelaySeconds: 30,
								PeriodSeconds:       10,
							},
							ReadinessProbe: &corev1.Probe{
								ProbeHandler: corev1.ProbeHandler{
									HTTPGet: &corev1.HTTPGetAction{
										Path: "/ready",
										Port: intstr.FromString("http"),
									},
								},
								InitialDelaySeconds: 5,
								PeriodSeconds:       5,
							},
						},
					},
					SecurityContext: &corev1.PodSecurityContext{
						RunAsNonRoot: &[]bool{true}[0],
						RunAsUser:    &[]int64{1000}[0],
						FSGroup:      &[]int64{2000}[0],
					},
				},
			},
		}

		return nil
	})

	if err != nil {
		return err
	}

	if op != controllerutil.OperationResultNone {
		log := ctrl.LoggerFrom(ctx)
		log.Info("Deployment reconciled", "operation", op)
	}

	return nil
}

func (r *WebAppReconciler) reconcileService(ctx context.Context, webapp *platformv1.WebApp) error {
	service := &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      webapp.Name,
			Namespace: webapp.Namespace,
		},
	}

	op, err := controllerutil.CreateOrUpdate(ctx, r.Client, service, func() error {
		if err := controllerutil.SetControllerReference(webapp, service, r.Scheme); err != nil {
			return err
		}

		service.Spec = corev1.ServiceSpec{
			Selector: map[string]string{
				"app": webapp.Name,
			},
			Ports: []corev1.ServicePort{
				{
					Name:       "http",
					Port:       80,
					TargetPort: intstr.FromString("http"),
					Protocol:   corev1.ProtocolTCP,
				},
			},
			Type: corev1.ServiceTypeClusterIP,
		}

		return nil
	})

	if err != nil {
		return err
	}

	if op != controllerutil.OperationResultNone {
		log := ctrl.LoggerFrom(ctx)
		log.Info("Service reconciled", "operation", op)
	}

	return nil
}

func (r *WebAppReconciler) handleDeletion(ctx context.Context, webapp *platformv1.WebApp) (ctrl.Result, error) {
	log := ctrl.LoggerFrom(ctx)
	log.Info("Handling WebApp deletion")

	// Perform cleanup operations here
	// For example, cleanup external resources, notify external systems, etc.

	// Remove finalizer to allow deletion
	controllerutil.RemoveFinalizer(webapp, platformv1.WebAppFinalizer)
	if err := r.Update(ctx, webapp); err != nil {
		log.Error(err, "Failed to remove finalizer")
		return ctrl.Result{}, err
	}

	r.Recorder.Event(webapp, corev1.EventTypeNormal, "Deleted", "WebApp deleted successfully")
	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *WebAppReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&platformv1.WebApp{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.ConfigMap{}).
		Owns(&autoscalingv2.HorizontalPodAutoscaler{}).
		Owns(&policyv1.PodDisruptionBudget{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: r.MaxConcurrentReconciles,
		}).
		Complete(r)
}
