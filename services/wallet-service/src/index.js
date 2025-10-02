const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const { createPrometheusMetrics } = require('./infrastructure/metrics');
const { initializeTracing } = require('./infrastructure/tracing');
const { connectDatabase } = require('./infrastructure/database');
const { connectRedis } = require('./infrastructure/redis');
const { createKafkaProducer } = require('./infrastructure/kafka');
const { OutboxProcessor } = require('./services/outboxProcessor');
const { WalletService } = require('./services/walletService');
const walletRoutes = require('./routes/walletRoutes');
const sagaRoutes = require('./routes/sagaRoutes');
const healthRoutes = require('./routes/healthRoutes');
const logger = require('./utils/logger');
const config = require('./config');

class WalletServiceApp {
  constructor() {
    this.app = express();
    this.server = null;
    this.outboxProcessor = null;
  }

  async initialize() {
    try {
      // Initialize tracing
      await initializeTracing();

      // Connect to databases
      await connectDatabase();
      await connectRedis();

      // Initialize Kafka
      const kafkaProducer = await createKafkaProducer();

      // Initialize services
      const walletService = new WalletService();
      this.outboxProcessor = new OutboxProcessor(kafkaProducer);

      // Setup middleware
      this.setupMiddleware();

      // Setup routes
      this.setupRoutes(walletService);

      // Start outbox processor
      await this.outboxProcessor.start();

      logger.info('Wallet Service initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize Wallet Service:', error);
      throw error;
    }
  }

  setupMiddleware() {
    // Security middleware
    this.app.use(helmet());
    this.app.use(cors());
    this.app.use(compression());

    // Rate limiting
    const limiter = rateLimit({
      windowMs: 15 * 60 * 1000, // 15 minutes
      max: 100, // limit each IP to 100 requests per windowMs
      message: 'Too many requests from this IP, please try again later.',
    });
    this.app.use('/api/', limiter);

    // Body parsing
    this.app.use(express.json({ limit: '10mb' }));
    this.app.use(express.urlencoded({ extended: true }));

    // Logging middleware
    this.app.use((req, res, next) => {
      const start = Date.now();
      res.on('finish', () => {
        const duration = Date.now() - start;
        logger.info(`${req.method} ${req.path} ${res.statusCode} ${duration}ms`);
      });
      next();
    });

    // Metrics middleware
    const { metricsMiddleware, register } = createPrometheusMetrics();
    this.app.use(metricsMiddleware);

    // Metrics endpoint
    this.app.get('/metrics', async (req, res) => {
      res.set('Content-Type', register.contentType);
      res.end(await register.metrics());
    });
  }

  setupRoutes(walletService) {
    // Health check routes
    this.app.use('/health', healthRoutes);

    // API routes
    this.app.use('/api/v1/wallets', walletRoutes(walletService));
    this.app.use('/api/v1/saga', sagaRoutes(walletService));

    // Error handling middleware
    this.app.use((error, req, res, next) => {
      logger.error('Unhandled error:', error);
      
      if (error.name === 'ValidationError') {
        return res.status(400).json({
          error: 'Validation Error',
          message: error.message,
          details: error.details,
        });
      }

      if (error.name === 'CastError') {
        return res.status(400).json({
          error: 'Invalid ID format',
          message: 'The provided ID is not valid',
        });
      }

      res.status(500).json({
        error: 'Internal Server Error',
        message: 'An unexpected error occurred',
        requestId: req.headers['x-request-id'],
      });
    });

    // 404 handler
    this.app.use('*', (req, res) => {
      res.status(404).json({
        error: 'Not Found',
        message: `Route ${req.method} ${req.originalUrl} not found`,
      });
    });
  }

  async start() {
    const port = config.port || 3003;
    
    this.server = this.app.listen(port, () => {
      logger.info(`Wallet Service listening on port ${port}`);
      logger.info(`Health check available at http://localhost:${port}/health`);
      logger.info(`Metrics available at http://localhost:${port}/metrics`);
    });

    // Graceful shutdown
    process.on('SIGTERM', () => this.shutdown());
    process.on('SIGINT', () => this.shutdown());
  }

  async shutdown() {
    logger.info('Shutting down Wallet Service...');

    try {
      // Stop accepting new requests
      if (this.server) {
        await new Promise((resolve) => {
          this.server.close(resolve);
        });
      }

      // Stop outbox processor
      if (this.outboxProcessor) {
        await this.outboxProcessor.stop();
      }

      // Close database connections
      const mongoose = require('mongoose');
      await mongoose.connection.close();

      logger.info('Wallet Service shut down successfully');
      process.exit(0);
    } catch (error) {
      logger.error('Error during shutdown:', error);
      process.exit(1);
    }
  }
}

// Start the application
async function main() {
  const app = new WalletServiceApp();
  
  try {
    await app.initialize();
    await app.start();
  } catch (error) {
    logger.error('Failed to start Wallet Service:', error);
    process.exit(1);
  }
}

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  logger.error('Uncaught Exception:', error);
  process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
  process.exit(1);
});

if (require.main === module) {
  main();
}

module.exports = WalletServiceApp;
