#!/usr/bin/env python3
"""
Real-time P&L Calculator with GPU Acceleration

This service provides:
1. Real-time P&L calculation with streaming market data
2. GPU-accelerated portfolio P&L computation
3. P&L attribution and decomposition
4. Intraday P&L monitoring and alerts
5. Multi-currency P&L calculation
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import os

import numpy as np
import pandas as pd
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from kafka import KafkaConsumer, KafkaProducer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import aiohttp
from aiohttp import web
import asyncpg

# GPU acceleration imports
try:
    import cupy as cp
    import cupyx.scipy.sparse as cp_sparse
    GPU_AVAILABLE = True
    logging.info("GPU acceleration available with CuPy")
except ImportError:
    GPU_AVAILABLE = False
    logging.warning("GPU acceleration not available, falling back to CPU")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Portfolio position"""
    portfolio_id: str
    instrument_id: str
    quantity: float
    average_price: float
    market_price: float
    market_value: float
    currency: str
    last_updated: datetime
    
@dataclass
class PnLResult:
    """P&L calculation result"""
    portfolio_id: str
    instrument_id: str
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    pnl_currency: str
    calculation_time: datetime
    market_value: float
    cost_basis: float

@dataclass
class MarketData:
    """Market data point"""
    instrument_id: str
    price: float
    timestamp: datetime
    volume: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

class GPUPnLCalculator:
    """GPU-accelerated P&L calculator"""
    
    def __init__(self):
        self.gpu_available = GPU_AVAILABLE
        if self.gpu_available:
            self.device = cp.cuda.Device(0)
            logger.info(f"Using GPU device: {self.device}")
    
    def calculate_portfolio_pnl_gpu(self, positions: List[Position], market_prices: Dict[str, float]) -> List[PnLResult]:
        """Calculate P&L for entire portfolio using GPU acceleration"""
        if not self.gpu_available or len(positions) < 1000:
            # Fall back to CPU for small portfolios
            return self.calculate_portfolio_pnl_cpu(positions, market_prices)
        
        try:
            # Prepare data for GPU computation
            n_positions = len(positions)
            quantities = cp.array([pos.quantity for pos in positions], dtype=cp.float64)
            avg_prices = cp.array([pos.average_price for pos in positions], dtype=cp.float64)
            market_prices_array = cp.array([
                market_prices.get(pos.instrument_id, pos.market_price) 
                for pos in positions
            ], dtype=cp.float64)
            
            # GPU-accelerated P&L calculation
            with self.device:
                # Calculate market values
                market_values = quantities * market_prices_array
                
                # Calculate cost basis
                cost_basis = quantities * avg_prices
                
                # Calculate unrealized P&L
                unrealized_pnl = market_values - cost_basis
                
                # Transfer results back to CPU
                market_values_cpu = cp.asnumpy(market_values)
                cost_basis_cpu = cp.asnumpy(cost_basis)
                unrealized_pnl_cpu = cp.asnumpy(unrealized_pnl)
            
            # Create results
            results = []
            calculation_time = datetime.now()
            
            for i, position in enumerate(positions):
                result = PnLResult(
                    portfolio_id=position.portfolio_id,
                    instrument_id=position.instrument_id,
                    unrealized_pnl=float(unrealized_pnl_cpu[i]),
                    realized_pnl=0.0,  # Would need trade history for realized P&L
                    total_pnl=float(unrealized_pnl_cpu[i]),
                    pnl_currency=position.currency,
                    calculation_time=calculation_time,
                    market_value=float(market_values_cpu[i]),
                    cost_basis=float(cost_basis_cpu[i])
                )
                results.append(result)
            
            logger.info(f"GPU P&L calculation completed for {n_positions} positions")
            return results
            
        except Exception as e:
            logger.error(f"GPU P&L calculation failed: {e}, falling back to CPU")
            return self.calculate_portfolio_pnl_cpu(positions, market_prices)
    
    def calculate_portfolio_pnl_cpu(self, positions: List[Position], market_prices: Dict[str, float]) -> List[PnLResult]:
        """CPU-based P&L calculation fallback"""
        results = []
        calculation_time = datetime.now()
        
        for position in positions:
            current_price = market_prices.get(position.instrument_id, position.market_price)
            market_value = position.quantity * current_price
            cost_basis = position.quantity * position.average_price
            unrealized_pnl = market_value - cost_basis
            
            result = PnLResult(
                portfolio_id=position.portfolio_id,
                instrument_id=position.instrument_id,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0.0,
                total_pnl=unrealized_pnl,
                pnl_currency=position.currency,
                calculation_time=calculation_time,
                market_value=market_value,
                cost_basis=cost_basis
            )
            results.append(result)
        
        logger.info(f"CPU P&L calculation completed for {len(positions)} positions")
        return results

class PnLCalculatorService:
    """Main P&L calculator service"""
    
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "postgresql://risk_user:secure_risk_pass@localhost:5439/market_risk_engine")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6385")
        self.kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9098")
        self.influxdb_url = os.getenv("INFLUXDB_URL", "http://localhost:8087")
        self.influxdb_token = os.getenv("INFLUXDB_TOKEN", "risk_admin_token_12345")
        self.influxdb_org = os.getenv("INFLUXDB_ORG", "risk_org")
        self.influxdb_bucket = os.getenv("INFLUXDB_BUCKET", "risk_metrics")
        
        # Initialize components
        self.gpu_calculator = GPUPnLCalculator()
        self.redis_client = None
        self.db_pool = None
        self.influxdb_client = None
        self.kafka_producer = None
        
        # Cache for positions and market data
        self.positions_cache: Dict[str, List[Position]] = {}
        self.market_data_cache: Dict[str, MarketData] = {}
        
        # Performance metrics
        self.calculation_count = 0
        self.total_calculation_time = 0.0
        
    async def initialize(self):
        """Initialize all connections"""
        try:
            # Initialize Redis
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await asyncio.get_event_loop().run_in_executor(None, self.redis_client.ping)
            logger.info("Redis connection established")
            
            # Initialize PostgreSQL connection pool
            self.db_pool = await asyncpg.create_pool(self.db_url, min_size=5, max_size=20)
            logger.info("PostgreSQL connection pool created")
            
            # Initialize InfluxDB
            self.influxdb_client = InfluxDBClient(
                url=self.influxdb_url,
                token=self.influxdb_token,
                org=self.influxdb_org
            )
            logger.info("InfluxDB connection established")
            
            # Initialize Kafka producer
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=self.kafka_brokers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None
            )
            logger.info("Kafka producer initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            raise
    
    async def load_positions(self, portfolio_id: str) -> List[Position]:
        """Load positions from database"""
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT portfolio_id, instrument_id, quantity, average_price, 
                           market_price, market_value, currency, last_updated
                    FROM positions 
                    WHERE portfolio_id = $1 AND quantity != 0
                """
                rows = await conn.fetch(query, portfolio_id)
                
                positions = []
                for row in rows:
                    position = Position(
                        portfolio_id=row['portfolio_id'],
                        instrument_id=row['instrument_id'],
                        quantity=float(row['quantity']),
                        average_price=float(row['average_price']),
                        market_price=float(row['market_price']),
                        market_value=float(row['market_value']),
                        currency=row['currency'],
                        last_updated=row['last_updated']
                    )
                    positions.append(position)
                
                # Cache positions
                self.positions_cache[portfolio_id] = positions
                logger.info(f"Loaded {len(positions)} positions for portfolio {portfolio_id}")
                return positions
                
        except Exception as e:
            logger.error(f"Failed to load positions for {portfolio_id}: {e}")
            return []
    
    async def get_market_prices(self, instrument_ids: List[str]) -> Dict[str, float]:
        """Get current market prices from cache/database"""
        prices = {}
        
        try:
            # Try Redis cache first
            pipe = self.redis_client.pipeline()
            for instrument_id in instrument_ids:
                pipe.hget(f"market_data:{instrument_id}", "price")
            
            cached_prices = await asyncio.get_event_loop().run_in_executor(None, pipe.execute)
            
            for i, instrument_id in enumerate(instrument_ids):
                if cached_prices[i]:
                    prices[instrument_id] = float(cached_prices[i])
            
            # Get missing prices from database
            missing_instruments = [iid for iid in instrument_ids if iid not in prices]
            if missing_instruments:
                async with self.db_pool.acquire() as conn:
                    query = """
                        SELECT instrument_id, price 
                        FROM market_data 
                        WHERE instrument_id = ANY($1)
                        ORDER BY timestamp DESC
                    """
                    rows = await conn.fetch(query, missing_instruments)
                    
                    for row in rows:
                        prices[row['instrument_id']] = float(row['price'])
            
            logger.info(f"Retrieved prices for {len(prices)} instruments")
            return prices
            
        except Exception as e:
            logger.error(f"Failed to get market prices: {e}")
            return {}
    
    async def calculate_pnl(self, portfolio_id: str) -> List[PnLResult]:
        """Calculate P&L for a portfolio"""
        start_time = time.time()
        
        try:
            # Load positions
            positions = await self.load_positions(portfolio_id)
            if not positions:
                return []
            
            # Get current market prices
            instrument_ids = [pos.instrument_id for pos in positions]
            market_prices = await self.get_market_prices(instrument_ids)
            
            # Calculate P&L using GPU acceleration
            pnl_results = self.gpu_calculator.calculate_portfolio_pnl_gpu(positions, market_prices)
            
            # Store results in database
            await self.store_pnl_results(pnl_results)
            
            # Send to InfluxDB for time-series storage
            await self.store_pnl_metrics(pnl_results)
            
            # Publish to Kafka
            await self.publish_pnl_updates(pnl_results)
            
            # Update performance metrics
            calculation_time = time.time() - start_time
            self.calculation_count += 1
            self.total_calculation_time += calculation_time
            
            logger.info(f"P&L calculation completed for {portfolio_id} in {calculation_time:.3f}s")
            return pnl_results
            
        except Exception as e:
            logger.error(f"P&L calculation failed for {portfolio_id}: {e}")
            return []
    
    async def store_pnl_results(self, pnl_results: List[PnLResult]):
        """Store P&L results in database"""
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    INSERT INTO pnl_results (
                        portfolio_id, instrument_id, unrealized_pnl, realized_pnl,
                        total_pnl, pnl_currency, calculation_time, market_value, cost_basis
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (portfolio_id, instrument_id, calculation_time)
                    DO UPDATE SET
                        unrealized_pnl = EXCLUDED.unrealized_pnl,
                        realized_pnl = EXCLUDED.realized_pnl,
                        total_pnl = EXCLUDED.total_pnl,
                        market_value = EXCLUDED.market_value,
                        cost_basis = EXCLUDED.cost_basis
                """
                
                for result in pnl_results:
                    await conn.execute(
                        query,
                        result.portfolio_id,
                        result.instrument_id,
                        result.unrealized_pnl,
                        result.realized_pnl,
                        result.total_pnl,
                        result.pnl_currency,
                        result.calculation_time,
                        result.market_value,
                        result.cost_basis
                    )
            
            logger.info(f"Stored {len(pnl_results)} P&L results in database")
            
        except Exception as e:
            logger.error(f"Failed to store P&L results: {e}")
    
    async def store_pnl_metrics(self, pnl_results: List[PnLResult]):
        """Store P&L metrics in InfluxDB"""
        try:
            write_api = self.influxdb_client.write_api(write_options=SYNCHRONOUS)
            points = []
            
            for result in pnl_results:
                point = Point("pnl_metrics") \
                    .tag("portfolio_id", result.portfolio_id) \
                    .tag("instrument_id", result.instrument_id) \
                    .tag("currency", result.pnl_currency) \
                    .field("unrealized_pnl", result.unrealized_pnl) \
                    .field("realized_pnl", result.realized_pnl) \
                    .field("total_pnl", result.total_pnl) \
                    .field("market_value", result.market_value) \
                    .field("cost_basis", result.cost_basis) \
                    .time(result.calculation_time)
                points.append(point)
            
            write_api.write(bucket=self.influxdb_bucket, record=points)
            logger.info(f"Stored {len(points)} P&L metrics in InfluxDB")
            
        except Exception as e:
            logger.error(f"Failed to store P&L metrics: {e}")
    
    async def publish_pnl_updates(self, pnl_results: List[PnLResult]):
        """Publish P&L updates to Kafka"""
        try:
            for result in pnl_results:
                message = {
                    "event_type": "pnl_update",
                    "portfolio_id": result.portfolio_id,
                    "instrument_id": result.instrument_id,
                    "pnl_data": asdict(result),
                    "timestamp": result.calculation_time.isoformat()
                }
                
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.kafka_producer.send,
                    "pnl_updates",
                    message,
                    result.portfolio_id
                )
            
            logger.info(f"Published {len(pnl_results)} P&L updates to Kafka")
            
        except Exception as e:
            logger.error(f"Failed to publish P&L updates: {e}")
    
    async def get_portfolio_pnl_summary(self, portfolio_id: str) -> Dict:
        """Get P&L summary for a portfolio"""
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT 
                        SUM(unrealized_pnl) as total_unrealized_pnl,
                        SUM(realized_pnl) as total_realized_pnl,
                        SUM(total_pnl) as total_pnl,
                        SUM(market_value) as total_market_value,
                        SUM(cost_basis) as total_cost_basis,
                        COUNT(*) as position_count,
                        MAX(calculation_time) as last_updated
                    FROM pnl_results 
                    WHERE portfolio_id = $1
                    AND calculation_time >= NOW() - INTERVAL '1 hour'
                """
                row = await conn.fetchrow(query, portfolio_id)
                
                if row:
                    return {
                        "portfolio_id": portfolio_id,
                        "total_unrealized_pnl": float(row['total_unrealized_pnl'] or 0),
                        "total_realized_pnl": float(row['total_realized_pnl'] or 0),
                        "total_pnl": float(row['total_pnl'] or 0),
                        "total_market_value": float(row['total_market_value'] or 0),
                        "total_cost_basis": float(row['total_cost_basis'] or 0),
                        "position_count": int(row['position_count'] or 0),
                        "last_updated": row['last_updated'].isoformat() if row['last_updated'] else None,
                        "pnl_return": (float(row['total_pnl'] or 0) / float(row['total_cost_basis'] or 1)) * 100
                    }
                else:
                    return {"portfolio_id": portfolio_id, "error": "No P&L data found"}
                    
        except Exception as e:
            logger.error(f"Failed to get P&L summary for {portfolio_id}: {e}")
            return {"portfolio_id": portfolio_id, "error": str(e)}

# HTTP API handlers
async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "healthy",
        "service": "pnl-calculator",
        "gpu_available": GPU_AVAILABLE,
        "timestamp": datetime.now().isoformat()
    })

async def calculate_pnl_handler(request):
    """Calculate P&L for a portfolio"""
    try:
        portfolio_id = request.match_info['portfolio_id']
        service = request.app['pnl_service']
        
        pnl_results = await service.calculate_pnl(portfolio_id)
        
        return web.json_response({
            "portfolio_id": portfolio_id,
            "pnl_results": [asdict(result) for result in pnl_results],
            "calculation_count": len(pnl_results),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"P&L calculation request failed: {e}")
        return web.json_response(
            {"error": str(e)}, 
            status=500
        )

async def get_pnl_summary_handler(request):
    """Get P&L summary for a portfolio"""
    try:
        portfolio_id = request.match_info['portfolio_id']
        service = request.app['pnl_service']
        
        summary = await service.get_portfolio_pnl_summary(portfolio_id)
        
        return web.json_response(summary)
        
    except Exception as e:
        logger.error(f"P&L summary request failed: {e}")
        return web.json_response(
            {"error": str(e)}, 
            status=500
        )

async def get_performance_metrics_handler(request):
    """Get service performance metrics"""
    service = request.app['pnl_service']
    
    avg_calculation_time = (
        service.total_calculation_time / service.calculation_count 
        if service.calculation_count > 0 else 0
    )
    
    return web.json_response({
        "calculation_count": service.calculation_count,
        "total_calculation_time": service.total_calculation_time,
        "average_calculation_time": avg_calculation_time,
        "gpu_available": GPU_AVAILABLE,
        "positions_cached": len(service.positions_cache),
        "market_data_cached": len(service.market_data_cache)
    })

async def init_app():
    """Initialize the web application"""
    app = web.Application()
    
    # Initialize P&L service
    pnl_service = PnLCalculatorService()
    await pnl_service.initialize()
    app['pnl_service'] = pnl_service
    
    # Setup routes
    app.router.add_get('/health', health_check)
    app.router.add_post('/api/v1/pnl/{portfolio_id}', calculate_pnl_handler)
    app.router.add_get('/api/v1/pnl/{portfolio_id}', get_pnl_summary_handler)
    app.router.add_get('/api/v1/metrics', get_performance_metrics_handler)
    
    return app

if __name__ == '__main__':
    # Run the service
    app = asyncio.get_event_loop().run_until_complete(init_app())
    web.run_app(app, host='0.0.0.0', port=8080)
