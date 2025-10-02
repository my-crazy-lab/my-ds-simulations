#!/usr/bin/env python3
"""
Blue/Green Deployment System for RAG Index
Enables zero-downtime index updates with atomic swaps
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import redis.asyncio as redis
from pymilvus import connections, Collection, utility
import prometheus_client
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Metrics
DEPLOYMENT_OPERATIONS = Counter('rag_deployment_operations_total', 'Deployment operations', ['operation', 'status'])
ACTIVE_INDEX_GAUGE = Gauge('rag_active_index', 'Currently active index', ['version', 'color'])
DEPLOYMENT_DURATION = Histogram('rag_deployment_duration_seconds', 'Time spent on deployments')

class IndexColor(Enum):
    BLUE = "blue"
    GREEN = "green"

class DeploymentStatus(Enum):
    PREPARING = "preparing"
    BUILDING = "building"
    TESTING = "testing"
    READY = "ready"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    FAILED = "failed"

class IndexMetadata:
    """Metadata for index versions"""
    
    def __init__(self, version: str, color: IndexColor, status: DeploymentStatus):
        self.version = version
        self.color = color
        self.status = status
        self.created_at = datetime.now().isoformat()
        self.activated_at: Optional[str] = None
        self.document_count = 0
        self.health_score = 0.0
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            'version': self.version,
            'color': self.color.value,
            'status': self.status.value,
            'created_at': self.created_at,
            'activated_at': self.activated_at,
            'document_count': self.document_count,
            'health_score': self.health_score,
            'last_updated': self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'IndexMetadata':
        metadata = cls(
            version=data['version'],
            color=IndexColor(data['color']),
            status=DeploymentStatus(data['status'])
        )
        metadata.created_at = data.get('created_at', metadata.created_at)
        metadata.activated_at = data.get('activated_at')
        metadata.document_count = data.get('document_count', 0)
        metadata.health_score = data.get('health_score', 0.0)
        metadata.last_updated = data.get('last_updated', metadata.last_updated)
        return metadata

class BlueGreenDeploymentManager:
    """Manages blue/green deployments for RAG indices"""
    
    def __init__(self, redis_url: str, milvus_host: str, milvus_port: int, collection_prefix: str):
        self.redis_url = redis_url
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.collection_prefix = collection_prefix
        self.redis_client = None
        self._connect_milvus()
    
    def _connect_milvus(self):
        """Connect to Milvus"""
        try:
            connections.connect(
                alias="deployment",
                host=self.milvus_host,
                port=self.milvus_port
            )
            logger.info("Connected to Milvus for deployment management")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    async def _get_redis_client(self) -> redis.Redis:
        """Get Redis client"""
        if not self.redis_client:
            self.redis_client = redis.from_url(self.redis_url)
        return self.redis_client
    
    async def get_active_index(self) -> Optional[IndexMetadata]:
        """Get currently active index metadata"""
        try:
            redis_client = await self._get_redis_client()
            active_data = await redis_client.get("rag:active_index")
            
            if active_data:
                data = json.loads(active_data)
                return IndexMetadata.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting active index: {e}")
            return None
    
    async def get_standby_index(self) -> Optional[IndexMetadata]:
        """Get standby index metadata"""
        try:
            redis_client = await self._get_redis_client()
            standby_data = await redis_client.get("rag:standby_index")
            
            if standby_data:
                data = json.loads(standby_data)
                return IndexMetadata.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting standby index: {e}")
            return None
    
    async def create_new_index(self, version: str) -> Tuple[IndexMetadata, str]:
        """Create a new index for deployment"""
        try:
            # Determine color for new index
            active_index = await self.get_active_index()
            if active_index:
                new_color = IndexColor.GREEN if active_index.color == IndexColor.BLUE else IndexColor.BLUE
            else:
                new_color = IndexColor.BLUE
            
            # Create index metadata
            metadata = IndexMetadata(version, new_color, DeploymentStatus.PREPARING)
            collection_name = f"{self.collection_prefix}_{new_color.value}_{version}"
            
            # Store metadata in Redis
            redis_client = await self._get_redis_client()
            await redis_client.setex(
                f"rag:index:{collection_name}",
                86400 * 7,  # 7 days TTL
                json.dumps(metadata.to_dict())
            )
            
            logger.info(f"Created new index metadata: {collection_name}")
            DEPLOYMENT_OPERATIONS.labels(operation='create_index', status='success').inc()
            
            return metadata, collection_name
            
        except Exception as e:
            logger.error(f"Error creating new index: {e}")
            DEPLOYMENT_OPERATIONS.labels(operation='create_index', status='error').inc()
            raise
    
    async def update_index_status(self, collection_name: str, status: DeploymentStatus, 
                                document_count: int = 0, health_score: float = 0.0):
        """Update index status and metrics"""
        try:
            redis_client = await self._get_redis_client()
            metadata_key = f"rag:index:{collection_name}"
            
            # Get current metadata
            metadata_data = await redis_client.get(metadata_key)
            if not metadata_data:
                raise ValueError(f"Index metadata not found: {collection_name}")
            
            metadata = IndexMetadata.from_dict(json.loads(metadata_data))
            
            # Update status and metrics
            metadata.status = status
            metadata.document_count = document_count
            metadata.health_score = health_score
            metadata.last_updated = datetime.now().isoformat()
            
            if status == DeploymentStatus.ACTIVE:
                metadata.activated_at = datetime.now().isoformat()
            
            # Save updated metadata
            await redis_client.setex(metadata_key, 86400 * 7, json.dumps(metadata.to_dict()))
            
            logger.info(f"Updated index {collection_name} status to {status.value}")
            
        except Exception as e:
            logger.error(f"Error updating index status: {e}")
            raise
    
    async def run_health_check(self, collection_name: str) -> Tuple[bool, float, Dict]:
        """Run health check on an index"""
        try:
            # Check if collection exists and is loaded
            if not utility.has_collection(collection_name):
                return False, 0.0, {"error": "Collection does not exist"}
            
            collection = Collection(collection_name)
            
            # Check if collection is loaded
            if not collection.is_loaded:
                collection.load()
            
            # Basic health metrics
            num_entities = collection.num_entities
            
            # Perform a simple search to test functionality
            try:
                # Create a dummy embedding for testing
                dummy_embedding = [0.1] * 384  # Assuming 384-dimensional embeddings
                search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
                
                results = collection.search(
                    data=[dummy_embedding],
                    anns_field="embedding",
                    param=search_params,
                    limit=1,
                    timeout=5.0
                )
                
                search_success = True
                
            except Exception as search_error:
                logger.warning(f"Search test failed for {collection_name}: {search_error}")
                search_success = False
            
            # Calculate health score
            health_score = 0.0
            health_details = {
                "collection_exists": True,
                "collection_loaded": collection.is_loaded,
                "num_entities": num_entities,
                "search_functional": search_success,
            }
            
            if collection.is_loaded:
                health_score += 0.4
            if num_entities > 0:
                health_score += 0.3
            if search_success:
                health_score += 0.3
            
            is_healthy = health_score >= 0.7  # 70% threshold
            
            return is_healthy, health_score, health_details
            
        except Exception as e:
            logger.error(f"Health check failed for {collection_name}: {e}")
            return False, 0.0, {"error": str(e)}
    
    @DEPLOYMENT_DURATION.time()
    async def perform_atomic_swap(self, new_collection_name: str) -> bool:
        """Perform atomic swap to activate new index"""
        try:
            redis_client = await self._get_redis_client()
            
            # Get new index metadata
            new_metadata_data = await redis_client.get(f"rag:index:{new_collection_name}")
            if not new_metadata_data:
                raise ValueError(f"New index metadata not found: {new_collection_name}")
            
            new_metadata = IndexMetadata.from_dict(json.loads(new_metadata_data))
            
            # Run final health check
            is_healthy, health_score, health_details = await self.run_health_check(new_collection_name)
            if not is_healthy:
                logger.error(f"New index failed health check: {health_details}")
                await self.update_index_status(new_collection_name, DeploymentStatus.FAILED, 
                                             health_score=health_score)
                return False
            
            # Get current active index
            current_active = await self.get_active_index()
            
            # Atomic swap using Redis transaction
            async with redis_client.pipeline(transaction=True) as pipe:
                # Watch keys for atomic operation
                await pipe.watch("rag:active_index", "rag:standby_index")
                
                # Start transaction
                pipe.multi()
                
                # Update new index to active
                new_metadata.status = DeploymentStatus.ACTIVE
                new_metadata.activated_at = datetime.now().isoformat()
                await pipe.set("rag:active_index", json.dumps(new_metadata.to_dict()))
                
                # Move current active to standby (if exists)
                if current_active:
                    current_active.status = DeploymentStatus.DEPRECATED
                    await pipe.set("rag:standby_index", json.dumps(current_active.to_dict()))
                
                # Update index metadata
                await pipe.setex(f"rag:index:{new_collection_name}", 86400 * 7, 
                               json.dumps(new_metadata.to_dict()))
                
                # Execute transaction
                await pipe.execute()
            
            # Update Prometheus metrics
            ACTIVE_INDEX_GAUGE.labels(version=new_metadata.version, color=new_metadata.color.value).set(1)
            if current_active:
                ACTIVE_INDEX_GAUGE.labels(version=current_active.version, color=current_active.color.value).set(0)
            
            logger.info(f"Successfully swapped to new active index: {new_collection_name}")
            DEPLOYMENT_OPERATIONS.labels(operation='atomic_swap', status='success').inc()
            
            return True
            
        except Exception as e:
            logger.error(f"Atomic swap failed: {e}")
            DEPLOYMENT_OPERATIONS.labels(operation='atomic_swap', status='error').inc()
            return False
    
    async def rollback_deployment(self) -> bool:
        """Rollback to previous index version"""
        try:
            redis_client = await self._get_redis_client()
            
            # Get current active and standby indices
            active_index = await self.get_active_index()
            standby_index = await self.get_standby_index()
            
            if not standby_index:
                logger.error("No standby index available for rollback")
                return False
            
            # Verify standby index health
            standby_collection = f"{self.collection_prefix}_{standby_index.color.value}_{standby_index.version}"
            is_healthy, health_score, health_details = await self.run_health_check(standby_collection)
            
            if not is_healthy:
                logger.error(f"Standby index is not healthy for rollback: {health_details}")
                return False
            
            # Perform rollback swap
            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.watch("rag:active_index", "rag:standby_index")
                
                pipe.multi()
                
                # Swap active and standby
                standby_index.status = DeploymentStatus.ACTIVE
                standby_index.activated_at = datetime.now().isoformat()
                await pipe.set("rag:active_index", json.dumps(standby_index.to_dict()))
                
                if active_index:
                    active_index.status = DeploymentStatus.DEPRECATED
                    await pipe.set("rag:standby_index", json.dumps(active_index.to_dict()))
                
                await pipe.execute()
            
            logger.info(f"Successfully rolled back to index version {standby_index.version}")
            DEPLOYMENT_OPERATIONS.labels(operation='rollback', status='success').inc()
            
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            DEPLOYMENT_OPERATIONS.labels(operation='rollback', status='error').inc()
            return False
    
    async def cleanup_old_indices(self, keep_versions: int = 3) -> int:
        """Clean up old index versions"""
        try:
            redis_client = await self._get_redis_client()
            
            # Get all index keys
            index_keys = await redis_client.keys(f"rag:index:{self.collection_prefix}_*")
            
            if len(index_keys) <= keep_versions:
                return 0
            
            # Get metadata for all indices
            indices_metadata = []
            for key in index_keys:
                metadata_data = await redis_client.get(key)
                if metadata_data:
                    metadata = IndexMetadata.from_dict(json.loads(metadata_data))
                    collection_name = key.decode().split(":")[-1]
                    indices_metadata.append((collection_name, metadata))
            
            # Sort by creation time (oldest first)
            indices_metadata.sort(key=lambda x: x[1].created_at)
            
            # Keep active, standby, and most recent versions
            active_index = await self.get_active_index()
            standby_index = await self.get_standby_index()
            
            protected_versions = set()
            if active_index:
                protected_versions.add(active_index.version)
            if standby_index:
                protected_versions.add(standby_index.version)
            
            # Add most recent versions to protected set
            recent_versions = sorted(
                [metadata.version for _, metadata in indices_metadata],
                reverse=True
            )[:keep_versions]
            protected_versions.update(recent_versions)
            
            # Clean up old indices
            cleaned_count = 0
            for collection_name, metadata in indices_metadata:
                if metadata.version not in protected_versions:
                    try:
                        # Drop Milvus collection
                        if utility.has_collection(collection_name):
                            utility.drop_collection(collection_name)
                        
                        # Remove Redis metadata
                        await redis_client.delete(f"rag:index:{collection_name}")
                        
                        cleaned_count += 1
                        logger.info(f"Cleaned up old index: {collection_name}")
                        
                    except Exception as e:
                        logger.error(f"Error cleaning up index {collection_name}: {e}")
            
            DEPLOYMENT_OPERATIONS.labels(operation='cleanup', status='success').inc(cleaned_count)
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            DEPLOYMENT_OPERATIONS.labels(operation='cleanup', status='error').inc()
            return 0
    
    async def get_deployment_status(self) -> Dict:
        """Get current deployment status"""
        try:
            active_index = await self.get_active_index()
            standby_index = await self.get_standby_index()
            
            status = {
                "active_index": active_index.to_dict() if active_index else None,
                "standby_index": standby_index.to_dict() if standby_index else None,
                "deployment_timestamp": datetime.now().isoformat(),
            }
            
            # Add health check results
            if active_index:
                active_collection = f"{self.collection_prefix}_{active_index.color.value}_{active_index.version}"
                is_healthy, health_score, health_details = await self.run_health_check(active_collection)
                status["active_index_health"] = {
                    "is_healthy": is_healthy,
                    "health_score": health_score,
                    "details": health_details,
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting deployment status: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """Close connections"""
        if self.redis_client:
            await self.redis_client.close()
