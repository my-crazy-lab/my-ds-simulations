import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import compression from 'compression';
import rateLimit from 'express-rate-limit';
import { config } from '@/config/config';
import { logger } from '@/utils/logger';
import { connectDatabase } from '@/infrastructure/database/mongodb';
import { KafkaService } from '@/infrastructure/messaging/kafka-service';
import { RedisService } from '@/infrastructure/cache/redis-service';
import { SagaOrchestrator } from '@/application/saga/saga-orchestrator';
import { OutboxProcessor } from '@/infrastructure/outbox/outbox-processor';
import { BillingController } from '@/interfaces/controllers/billing-controller';
import { InvoiceController } from '@/interfaces/controllers/invoice-controller';
import { PaymentController } from '@/interfaces/controllers/payment-controller';
import { HealthController } from '@/interfaces/controllers/health-controller';
import { MetricsController } from '@/interfaces/controllers/metrics-controller';
import { errorHandler } from '@/interfaces/middleware/error-handler';
import { requestLogger } from '@/interfaces/middleware/request-logger';
import { tracingMiddleware } from '@/interfaces/middleware/tracing-middleware';
import { metricsMiddleware } from '@/interfaces/middleware/metrics-middleware';

class BillingServiceApp {
  private app: express.Application;
  private kafkaService: KafkaService;
  private redisService: RedisService;
  private sagaOrchestrator: SagaOrchestrator;
  private outboxProcessor: OutboxProcessor;

  constructor() {
    this.app = express();
    this.kafkaService = new KafkaService();
    this.redisService = new RedisService();
    this.sagaOrchestrator = new SagaOrchestrator(this.kafkaService, this.redisService);
    this.outboxProcessor = new OutboxProcessor(this.kafkaService);
  }

  public async initialize(): Promise<void> {
    try {
      // Connect to databases
      await connectDatabase();
      await this.redisService.connect();
      await this.kafkaService.connect();

      // Setup middleware
      this.setupMiddleware();

      // Setup routes
      this.setupRoutes();

      // Setup error handling
      this.setupErrorHandling();

      // Start background services
      await this.startBackgroundServices();

      logger.info('Billing Service initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize Billing Service:', error);
      throw error;
    }
  }

  private setupMiddleware(): void {
    // Security middleware
    this.app.use(helmet());
    this.app.use(cors({
      origin: config.cors.allowedOrigins,
      credentials: true,
    }));

    // Rate limiting
    const limiter = rateLimit({
      windowMs: 15 * 60 * 1000, // 15 minutes
      max: 1000, // limit each IP to 1000 requests per windowMs
      message: 'Too many requests from this IP, please try again later.',
    });
    this.app.use(limiter);

    // Compression and parsing
    this.app.use(compression());
    this.app.use(express.json({ limit: '10mb' }));
    this.app.use(express.urlencoded({ extended: true, limit: '10mb' }));

    // Observability middleware
    this.app.use(requestLogger);
    this.app.use(tracingMiddleware);
    this.app.use(metricsMiddleware);
  }

  private setupRoutes(): void {
    const billingController = new BillingController(this.sagaOrchestrator);
    const invoiceController = new InvoiceController();
    const paymentController = new PaymentController(this.sagaOrchestrator);
    const healthController = new HealthController();
    const metricsController = new MetricsController();

    // API routes
    this.app.use('/api/v1/billing', billingController.getRouter());
    this.app.use('/api/v1/invoices', invoiceController.getRouter());
    this.app.use('/api/v1/payments', paymentController.getRouter());

    // System routes
    this.app.use('/health', healthController.getRouter());
    this.app.use('/metrics', metricsController.getRouter());

    // Root route
    this.app.get('/', (req, res) => {
      res.json({
        service: 'billing-service',
        version: '1.0.0',
        status: 'running',
        timestamp: new Date().toISOString(),
      });
    });
  }

  private setupErrorHandling(): void {
    // 404 handler
    this.app.use('*', (req, res) => {
      res.status(404).json({
        error: 'Not Found',
        message: `Route ${req.originalUrl} not found`,
        timestamp: new Date().toISOString(),
      });
    });

    // Global error handler
    this.app.use(errorHandler);
  }

  private async startBackgroundServices(): Promise<void> {
    // Start Saga orchestrator
    await this.sagaOrchestrator.start();

    // Start outbox processor
    await this.outboxProcessor.start();

    // Setup Kafka event handlers
    await this.setupKafkaEventHandlers();

    logger.info('Background services started successfully');
  }

  private async setupKafkaEventHandlers(): Promise<void> {
    // Subscribe to relevant topics
    const topics = [
      'order-events',
      'payment-events',
      'account-events',
      'transaction-events',
      'saga-events',
    ];

    for (const topic of topics) {
      await this.kafkaService.subscribe(topic, async (message) => {
        try {
          await this.handleKafkaMessage(topic, message);
        } catch (error) {
          logger.error(`Error handling Kafka message from topic ${topic}:`, error);
        }
      });
    }
  }

  private async handleKafkaMessage(topic: string, message: any): Promise<void> {
    logger.debug(`Received message from topic ${topic}:`, message);

    switch (topic) {
      case 'order-events':
        await this.handleOrderEvent(message);
        break;
      case 'payment-events':
        await this.handlePaymentEvent(message);
        break;
      case 'account-events':
        await this.handleAccountEvent(message);
        break;
      case 'transaction-events':
        await this.handleTransactionEvent(message);
        break;
      case 'saga-events':
        await this.sagaOrchestrator.handleSagaEvent(message);
        break;
      default:
        logger.warn(`Unknown topic: ${topic}`);
    }
  }

  private async handleOrderEvent(message: any): Promise<void> {
    const { eventType, data } = message;

    switch (eventType) {
      case 'OrderCreated':
        // Create billing record for new order
        logger.info('Processing OrderCreated event:', data);
        break;
      case 'OrderCompleted':
        // Generate invoice for completed order
        logger.info('Processing OrderCompleted event:', data);
        break;
      case 'OrderCancelled':
        // Handle order cancellation billing
        logger.info('Processing OrderCancelled event:', data);
        break;
      default:
        logger.debug(`Unhandled order event type: ${eventType}`);
    }
  }

  private async handlePaymentEvent(message: any): Promise<void> {
    const { eventType, data } = message;

    switch (eventType) {
      case 'PaymentProcessed':
        // Update billing status
        logger.info('Processing PaymentProcessed event:', data);
        break;
      case 'PaymentFailed':
        // Handle payment failure
        logger.info('Processing PaymentFailed event:', data);
        break;
      case 'PaymentRefunded':
        // Process refund
        logger.info('Processing PaymentRefunded event:', data);
        break;
      default:
        logger.debug(`Unhandled payment event type: ${eventType}`);
    }
  }

  private async handleAccountEvent(message: any): Promise<void> {
    const { eventType, data } = message;

    switch (eventType) {
      case 'AccountCreated':
        // Setup billing profile for new account
        logger.info('Processing AccountCreated event:', data);
        break;
      case 'AccountFrozen':
        // Suspend billing activities
        logger.info('Processing AccountFrozen event:', data);
        break;
      default:
        logger.debug(`Unhandled account event type: ${eventType}`);
    }
  }

  private async handleTransactionEvent(message: any): Promise<void> {
    const { eventType, data } = message;

    switch (eventType) {
      case 'TransactionCreated':
        // Track transaction for billing
        logger.info('Processing TransactionCreated event:', data);
        break;
      case 'TransactionCompleted':
        // Finalize billing for transaction
        logger.info('Processing TransactionCompleted event:', data);
        break;
      case 'TransactionFailed':
        // Handle transaction failure
        logger.info('Processing TransactionFailed event:', data);
        break;
      default:
        logger.debug(`Unhandled transaction event type: ${eventType}`);
    }
  }

  public async start(): Promise<void> {
    const port = config.server.port;
    
    this.app.listen(port, () => {
      logger.info(`Billing Service is running on port ${port}`);
      logger.info(`Environment: ${config.environment}`);
      logger.info(`Health check: http://localhost:${port}/health`);
      logger.info(`Metrics: http://localhost:${port}/metrics`);
    });
  }

  public async shutdown(): Promise<void> {
    logger.info('Shutting down Billing Service...');

    try {
      // Stop background services
      await this.outboxProcessor.stop();
      await this.sagaOrchestrator.stop();

      // Disconnect from services
      await this.kafkaService.disconnect();
      await this.redisService.disconnect();

      logger.info('Billing Service shut down successfully');
    } catch (error) {
      logger.error('Error during shutdown:', error);
      throw error;
    }
  }
}

// Application startup
async function main(): Promise<void> {
  const app = new BillingServiceApp();

  // Graceful shutdown handling
  process.on('SIGTERM', async () => {
    logger.info('SIGTERM received, shutting down gracefully...');
    await app.shutdown();
    process.exit(0);
  });

  process.on('SIGINT', async () => {
    logger.info('SIGINT received, shutting down gracefully...');
    await app.shutdown();
    process.exit(0);
  });

  process.on('unhandledRejection', (reason, promise) => {
    logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
    process.exit(1);
  });

  process.on('uncaughtException', (error) => {
    logger.error('Uncaught Exception:', error);
    process.exit(1);
  });

  try {
    await app.initialize();
    await app.start();
  } catch (error) {
    logger.error('Failed to start Billing Service:', error);
    process.exit(1);
  }
}

// Start the application
if (require.main === module) {
  main().catch((error) => {
    logger.error('Application startup failed:', error);
    process.exit(1);
  });
}

export { BillingServiceApp };
