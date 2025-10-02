package infrastructure

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/confluentinc/confluent-kafka-go/kafka"
	"github.com/sirupsen/logrus"
)

// KafkaProducer wraps Confluent Kafka producer
type KafkaProducer struct {
	producer *kafka.Producer
	logger   *logrus.Logger
}

// KafkaConsumer wraps Confluent Kafka consumer
type KafkaConsumer struct {
	consumer *kafka.Consumer
	logger   *logrus.Logger
}

// NewKafkaProducer creates a new Kafka producer
func NewKafkaProducer(brokers []string) (*KafkaProducer, error) {
	config := &kafka.ConfigMap{
		"bootstrap.servers":   strings.Join(brokers, ","),
		"client.id":           "saga-orchestrator-producer",
		"acks":                "all",
		"retries":             3,
		"retry.backoff.ms":    100,
		"batch.size":          16384,
		"linger.ms":           5,
		"compression.type":    "snappy",
		"max.in.flight.requests.per.connection": 1,
		"enable.idempotence": true,
	}

	producer, err := kafka.NewProducer(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create Kafka producer: %w", err)
	}

	logger := logrus.New()
	logger.SetLevel(logrus.InfoLevel)

	return &KafkaProducer{
		producer: producer,
		logger:   logger,
	}, nil
}

// NewKafkaConsumer creates a new Kafka consumer
func NewKafkaConsumer(brokers []string, groupID string) (*KafkaConsumer, error) {
	config := &kafka.ConfigMap{
		"bootstrap.servers":        strings.Join(brokers, ","),
		"group.id":                 groupID,
		"client.id":                "saga-orchestrator-consumer",
		"auto.offset.reset":        "earliest",
		"enable.auto.commit":       false,
		"session.timeout.ms":       30000,
		"heartbeat.interval.ms":    3000,
		"max.poll.interval.ms":     300000,
		"fetch.min.bytes":          1,
		"fetch.max.wait.ms":        500,
		"max.partition.fetch.bytes": 1048576,
	}

	consumer, err := kafka.NewConsumer(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create Kafka consumer: %w", err)
	}

	logger := logrus.New()
	logger.SetLevel(logrus.InfoLevel)

	return &KafkaConsumer{
		consumer: consumer,
		logger:   logger,
	}, nil
}

// Produce sends a message to a Kafka topic
func (p *KafkaProducer) Produce(ctx context.Context, topic, key string, value []byte, headers map[string]string) error {
	// Convert headers to Kafka headers
	var kafkaHeaders []kafka.Header
	for k, v := range headers {
		kafkaHeaders = append(kafkaHeaders, kafka.Header{
			Key:   k,
			Value: []byte(v),
		})
	}

	message := &kafka.Message{
		TopicPartition: kafka.TopicPartition{
			Topic:     &topic,
			Partition: kafka.PartitionAny,
		},
		Key:     []byte(key),
		Value:   value,
		Headers: kafkaHeaders,
	}

	// Delivery channel for async production
	deliveryChan := make(chan kafka.Event, 1)
	defer close(deliveryChan)

	err := p.producer.Produce(message, deliveryChan)
	if err != nil {
		return fmt.Errorf("failed to produce message: %w", err)
	}

	// Wait for delivery confirmation with timeout
	select {
	case e := <-deliveryChan:
		m := e.(*kafka.Message)
		if m.TopicPartition.Error != nil {
			return fmt.Errorf("delivery failed: %w", m.TopicPartition.Error)
		}
		p.logger.WithFields(logrus.Fields{
			"topic":     *m.TopicPartition.Topic,
			"partition": m.TopicPartition.Partition,
			"offset":    m.TopicPartition.Offset,
		}).Debug("Message delivered successfully")
		return nil
	case <-ctx.Done():
		return fmt.Errorf("message delivery timeout: %w", ctx.Err())
	case <-time.After(30 * time.Second):
		return fmt.Errorf("message delivery timeout after 30 seconds")
	}
}

// Subscribe subscribes to Kafka topics and processes messages
func (c *KafkaConsumer) Subscribe(ctx context.Context, topics []string, handler func(ctx context.Context, topic, key string, value []byte) error) error {
	err := c.consumer.SubscribeTopics(topics, nil)
	if err != nil {
		return fmt.Errorf("failed to subscribe to topics: %w", err)
	}

	c.logger.WithField("topics", topics).Info("Subscribed to Kafka topics")

	for {
		select {
		case <-ctx.Done():
			c.logger.Info("Consumer context cancelled, stopping")
			return ctx.Err()
		default:
			msg, err := c.consumer.ReadMessage(1000 * time.Millisecond)
			if err != nil {
				if err.(kafka.Error).Code() == kafka.ErrTimedOut {
					continue
				}
				c.logger.WithError(err).Error("Error reading message")
				continue
			}

			// Extract message details
			topic := *msg.TopicPartition.Topic
			key := string(msg.Key)
			value := msg.Value

			c.logger.WithFields(logrus.Fields{
				"topic":     topic,
				"partition": msg.TopicPartition.Partition,
				"offset":    msg.TopicPartition.Offset,
				"key":       key,
			}).Debug("Received message")

			// Process message
			if err := handler(ctx, topic, key, value); err != nil {
				c.logger.WithError(err).WithFields(logrus.Fields{
					"topic": topic,
					"key":   key,
				}).Error("Error processing message")
				// Continue processing other messages
				continue
			}

			// Commit message offset
			if err := c.consumer.CommitMessage(msg); err != nil {
				c.logger.WithError(err).Error("Error committing message")
			}
		}
	}
}

// Close closes the Kafka producer
func (p *KafkaProducer) Close() {
	if p.producer != nil {
		p.producer.Flush(5000) // Wait up to 5 seconds for pending messages
		p.producer.Close()
	}
}

// Close closes the Kafka consumer
func (c *KafkaConsumer) Close() {
	if c.consumer != nil {
		c.consumer.Close()
	}
}

// GetMetadata returns Kafka cluster metadata
func (p *KafkaProducer) GetMetadata(topic string, timeout time.Duration) (*kafka.Metadata, error) {
	return p.producer.GetMetadata(&topic, false, int(timeout.Milliseconds()))
}

// CreateTopic creates a Kafka topic (requires admin privileges)
func CreateTopic(brokers []string, topic string, numPartitions, replicationFactor int) error {
	config := &kafka.ConfigMap{
		"bootstrap.servers": strings.Join(brokers, ","),
	}

	adminClient, err := kafka.NewAdminClient(config)
	if err != nil {
		return fmt.Errorf("failed to create admin client: %w", err)
	}
	defer adminClient.Close()

	topicSpec := kafka.TopicSpecification{
		Topic:             topic,
		NumPartitions:     numPartitions,
		ReplicationFactor: replicationFactor,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	results, err := adminClient.CreateTopics(ctx, []kafka.TopicSpecification{topicSpec})
	if err != nil {
		return fmt.Errorf("failed to create topic: %w", err)
	}

	for _, result := range results {
		if result.Error.Code() != kafka.ErrNoError && result.Error.Code() != kafka.ErrTopicAlreadyExists {
			return fmt.Errorf("failed to create topic %s: %w", result.Topic, result.Error)
		}
	}

	return nil
}

// EnsureTopicsExist ensures that required topics exist
func EnsureTopicsExist(brokers []string) error {
	topics := []struct {
		name              string
		partitions        int
		replicationFactor int
	}{
		{"saga-events", 3, 1},
		{"inventory-events", 3, 1},
		{"payment-events", 3, 1},
		{"notification-events", 3, 1},
	}

	for _, topic := range topics {
		if err := CreateTopic(brokers, topic.name, topic.partitions, topic.replicationFactor); err != nil {
			return fmt.Errorf("failed to ensure topic %s exists: %w", topic.name, err)
		}
	}

	return nil
}
