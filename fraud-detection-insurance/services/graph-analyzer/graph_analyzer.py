#!/usr/bin/env python3
"""
Graph Analyzer Service

This service provides graph analytics capabilities for fraud detection including:
1. Network analysis and community detection
2. Entity resolution and relationship mapping
3. Suspicious pattern identification
4. Fraud ring detection
5. Centrality analysis and key actor identification
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
import os

import aiohttp
from aiohttp import web
import neo4j
from neo4j import GraphDatabase
import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import redis
import asyncio_mqtt
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
GRAPH_QUERIES = Counter('graph_queries_total', 'Total graph queries', ['query_type'])
QUERY_DURATION = Histogram('graph_query_duration_seconds', 'Graph query duration', ['query_type'])
FRAUD_RINGS_DETECTED = Counter('fraud_rings_detected_total', 'Total fraud rings detected')
SUSPICIOUS_PATTERNS = Counter('suspicious_patterns_total', 'Total suspicious patterns detected', ['pattern_type'])
ACTIVE_INVESTIGATIONS = Gauge('active_investigations', 'Number of active investigations')

@dataclass
class GraphNode:
    """Represents a node in the fraud detection graph"""
    id: str
    label: str
    properties: Dict[str, Any]
    risk_score: float = 0.0

@dataclass
class GraphRelationship:
    """Represents a relationship in the fraud detection graph"""
    start_node: str
    end_node: str
    relationship_type: str
    properties: Dict[str, Any]
    strength: float = 1.0

@dataclass
class FraudRing:
    """Represents a detected fraud ring"""
    ring_id: str
    members: List[str]
    center_node: str
    risk_score: float
    pattern_type: str
    detection_time: datetime
    evidence: List[Dict[str, Any]]

@dataclass
class NetworkAnalysisResult:
    """Results from network analysis"""
    analysis_id: str
    target_entity: str
    connected_entities: List[str]
    suspicious_patterns: List[Dict[str, Any]]
    risk_score: float
    fraud_rings: List[FraudRing]
    centrality_scores: Dict[str, float]
    analysis_time: datetime

class GraphAnalyzer:
    """Handles graph analytics for fraud detection"""
    
    def __init__(self):
        # Neo4j connection
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "fraud_detection_pass")
        
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        
        # Redis connection for caching
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6389")
        self.redis_client = redis.from_url(redis_url)
        
        # NetworkX graph for complex analysis
        self.nx_graph = nx.Graph()
        
        # Analysis parameters
        self.fraud_ring_threshold = 0.7
        self.suspicious_connection_threshold = 0.6
        self.max_analysis_depth = 4
        
    async def analyze_claim_network(self, claim_id: str, analysis_depth: int = 3) -> NetworkAnalysisResult:
        """Analyze the network around a specific claim"""
        with QUERY_DURATION.labels(query_type='network_analysis').time():
            GRAPH_QUERIES.labels(query_type='network_analysis').inc()
            
            analysis_id = str(uuid.uuid4())
            logger.info(f"Starting network analysis for claim {claim_id}, depth {analysis_depth}")
            
            # Get connected entities from Neo4j
            connected_entities = await self._get_connected_entities(claim_id, analysis_depth)
            
            # Build subgraph for analysis
            subgraph = await self._build_subgraph(claim_id, connected_entities)
            
            # Detect suspicious patterns
            suspicious_patterns = await self._detect_suspicious_patterns(subgraph)
            
            # Detect fraud rings
            fraud_rings = await self._detect_fraud_rings(subgraph)
            
            # Calculate centrality scores
            centrality_scores = await self._calculate_centrality_scores(subgraph)
            
            # Calculate overall risk score
            risk_score = await self._calculate_network_risk_score(
                suspicious_patterns, fraud_rings, centrality_scores
            )
            
            # Update metrics
            FRAUD_RINGS_DETECTED.inc(len(fraud_rings))
            for pattern in suspicious_patterns:
                SUSPICIOUS_PATTERNS.labels(pattern_type=pattern['type']).inc()
            
            result = NetworkAnalysisResult(
                analysis_id=analysis_id,
                target_entity=claim_id,
                connected_entities=connected_entities,
                suspicious_patterns=suspicious_patterns,
                risk_score=risk_score,
                fraud_rings=fraud_rings,
                centrality_scores=centrality_scores,
                analysis_time=datetime.now()
            )
            
            # Cache result
            await self._cache_analysis_result(analysis_id, result)
            
            logger.info(f"Network analysis completed for {claim_id}: risk_score={risk_score:.3f}")
            return result
    
    async def _get_connected_entities(self, claim_id: str, depth: int) -> List[str]:
        """Get entities connected to the claim within specified depth"""
        query = """
        MATCH path = (c:Claim {claim_id: $claim_id})-[*1..$depth]-(connected)
        WHERE connected <> c
        RETURN DISTINCT connected.id as entity_id, labels(connected) as labels
        LIMIT 1000
        """
        
        with self.driver.session() as session:
            result = session.run(query, claim_id=claim_id, depth=depth)
            entities = [record["entity_id"] for record in result]
            
        logger.info(f"Found {len(entities)} connected entities for claim {claim_id}")
        return entities
    
    async def _build_subgraph(self, claim_id: str, entities: List[str]) -> nx.Graph:
        """Build NetworkX subgraph for analysis"""
        subgraph = nx.Graph()
        
        # Add nodes
        all_entities = [claim_id] + entities
        for entity in all_entities:
            node_data = await self._get_node_properties(entity)
            subgraph.add_node(entity, **node_data)
        
        # Add relationships
        relationships = await self._get_relationships(all_entities)
        for rel in relationships:
            subgraph.add_edge(
                rel.start_node, 
                rel.end_node, 
                relationship_type=rel.relationship_type,
                strength=rel.strength,
                **rel.properties
            )
        
        logger.info(f"Built subgraph with {subgraph.number_of_nodes()} nodes and {subgraph.number_of_edges()} edges")
        return subgraph
    
    async def _get_node_properties(self, entity_id: str) -> Dict[str, Any]:
        """Get node properties from Neo4j"""
        query = """
        MATCH (n {id: $entity_id})
        RETURN labels(n) as labels, properties(n) as props
        """
        
        with self.driver.session() as session:
            result = session.run(query, entity_id=entity_id)
            record = result.single()
            
            if record:
                return {
                    "labels": record["labels"],
                    "properties": dict(record["props"])
                }
            return {}
    
    async def _get_relationships(self, entities: List[str]) -> List[GraphRelationship]:
        """Get relationships between entities"""
        query = """
        MATCH (a)-[r]->(b)
        WHERE a.id IN $entities AND b.id IN $entities
        RETURN a.id as start_node, b.id as end_node, 
               type(r) as rel_type, properties(r) as props
        """
        
        relationships = []
        with self.driver.session() as session:
            result = session.run(query, entities=entities)
            
            for record in result:
                rel = GraphRelationship(
                    start_node=record["start_node"],
                    end_node=record["end_node"],
                    relationship_type=record["rel_type"],
                    properties=dict(record["props"]),
                    strength=record["props"].get("strength", 1.0)
                )
                relationships.append(rel)
        
        return relationships
    
    async def _detect_suspicious_patterns(self, graph: nx.Graph) -> List[Dict[str, Any]]:
        """Detect suspicious patterns in the graph"""
        patterns = []
        
        # Pattern 1: High-degree nodes (potential fraud hubs)
        degree_centrality = nx.degree_centrality(graph)
        high_degree_threshold = 0.8
        
        for node, centrality in degree_centrality.items():
            if centrality > high_degree_threshold:
                patterns.append({
                    "type": "HIGH_DEGREE_HUB",
                    "entity": node,
                    "score": centrality,
                    "description": f"Entity with unusually high connectivity (centrality: {centrality:.3f})"
                })
        
        # Pattern 2: Dense subgraphs (potential fraud rings)
        try:
            communities = nx.community.greedy_modularity_communities(graph)
            for i, community in enumerate(communities):
                if len(community) >= 3:  # Minimum size for fraud ring
                    subgraph = graph.subgraph(community)
                    density = nx.density(subgraph)
                    
                    if density > 0.6:  # High density threshold
                        patterns.append({
                            "type": "DENSE_COMMUNITY",
                            "entities": list(community),
                            "score": density,
                            "description": f"Dense community of {len(community)} entities (density: {density:.3f})"
                        })
        except Exception as e:
            logger.warning(f"Community detection failed: {e}")
        
        # Pattern 3: Temporal clustering
        temporal_patterns = await self._detect_temporal_patterns(graph)
        patterns.extend(temporal_patterns)
        
        # Pattern 4: Geographic clustering
        geographic_patterns = await self._detect_geographic_patterns(graph)
        patterns.extend(geographic_patterns)
        
        logger.info(f"Detected {len(patterns)} suspicious patterns")
        return patterns
    
    async def _detect_temporal_patterns(self, graph: nx.Graph) -> List[Dict[str, Any]]:
        """Detect temporal clustering patterns"""
        patterns = []
        
        # Extract timestamps from node properties
        timestamps = []
        nodes_with_time = []
        
        for node in graph.nodes():
            node_data = graph.nodes[node]
            props = node_data.get("properties", {})
            
            if "incident_date" in props or "created_at" in props:
                timestamp_str = props.get("incident_date") or props.get("created_at")
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    timestamps.append(timestamp.timestamp())
                    nodes_with_time.append(node)
                except:
                    continue
        
        if len(timestamps) >= 3:
            # Use DBSCAN to find temporal clusters
            timestamps_array = np.array(timestamps).reshape(-1, 1)
            scaler = StandardScaler()
            scaled_timestamps = scaler.fit_transform(timestamps_array)
            
            clustering = DBSCAN(eps=0.5, min_samples=3).fit(scaled_timestamps)
            
            # Analyze clusters
            for cluster_id in set(clustering.labels_):
                if cluster_id != -1:  # Ignore noise points
                    cluster_nodes = [nodes_with_time[i] for i, label in enumerate(clustering.labels_) if label == cluster_id]
                    
                    if len(cluster_nodes) >= 3:
                        cluster_timestamps = [timestamps[i] for i, label in enumerate(clustering.labels_) if label == cluster_id]
                        time_span = max(cluster_timestamps) - min(cluster_timestamps)
                        
                        if time_span < 86400 * 7:  # Within 7 days
                            patterns.append({
                                "type": "TEMPORAL_CLUSTERING",
                                "entities": cluster_nodes,
                                "score": 1.0 - (time_span / (86400 * 7)),
                                "description": f"Temporal cluster of {len(cluster_nodes)} entities within {time_span/86400:.1f} days"
                            })
        
        return patterns
    
    async def _detect_geographic_patterns(self, graph: nx.Graph) -> List[Dict[str, Any]]:
        """Detect geographic clustering patterns"""
        patterns = []
        
        # Extract coordinates from node properties
        coordinates = []
        nodes_with_location = []
        
        for node in graph.nodes():
            node_data = graph.nodes[node]
            props = node_data.get("properties", {})
            
            if "latitude" in props and "longitude" in props:
                try:
                    lat = float(props["latitude"])
                    lon = float(props["longitude"])
                    coordinates.append([lat, lon])
                    nodes_with_location.append(node)
                except:
                    continue
        
        if len(coordinates) >= 3:
            # Use DBSCAN to find geographic clusters
            coordinates_array = np.array(coordinates)
            
            # Use distance-based clustering (eps in degrees, roughly 1km = 0.01 degrees)
            clustering = DBSCAN(eps=0.01, min_samples=3).fit(coordinates_array)
            
            # Analyze clusters
            for cluster_id in set(clustering.labels_):
                if cluster_id != -1:  # Ignore noise points
                    cluster_nodes = [nodes_with_location[i] for i, label in enumerate(clustering.labels_) if label == cluster_id]
                    
                    if len(cluster_nodes) >= 3:
                        cluster_coords = [coordinates[i] for i, label in enumerate(clustering.labels_) if label == cluster_id]
                        
                        # Calculate cluster radius
                        center = np.mean(cluster_coords, axis=0)
                        distances = [np.linalg.norm(coord - center) for coord in cluster_coords]
                        max_distance = max(distances)
                        
                        patterns.append({
                            "type": "GEOGRAPHIC_CLUSTERING",
                            "entities": cluster_nodes,
                            "score": max(0, 1.0 - max_distance),
                            "description": f"Geographic cluster of {len(cluster_nodes)} entities within {max_distance*111:.1f}km radius"
                        })
        
        return patterns
    
    async def _detect_fraud_rings(self, graph: nx.Graph) -> List[FraudRing]:
        """Detect potential fraud rings using community detection"""
        fraud_rings = []
        
        try:
            # Use multiple community detection algorithms
            communities_greedy = nx.community.greedy_modularity_communities(graph)
            
            for i, community in enumerate(communities_greedy):
                if len(community) >= 3:  # Minimum size for fraud ring
                    subgraph = graph.subgraph(community)
                    
                    # Calculate ring characteristics
                    density = nx.density(subgraph)
                    centrality = nx.degree_centrality(subgraph)
                    
                    # Find center node (highest centrality)
                    center_node = max(centrality.items(), key=lambda x: x[1])[0]
                    
                    # Calculate risk score based on density and other factors
                    risk_score = self._calculate_ring_risk_score(subgraph, density, centrality)
                    
                    if risk_score > self.fraud_ring_threshold:
                        # Collect evidence
                        evidence = await self._collect_ring_evidence(subgraph)
                        
                        fraud_ring = FraudRing(
                            ring_id=f"RING_{uuid.uuid4().hex[:8]}",
                            members=list(community),
                            center_node=center_node,
                            risk_score=risk_score,
                            pattern_type="COMMUNITY_DETECTION",
                            detection_time=datetime.now(),
                            evidence=evidence
                        )
                        
                        fraud_rings.append(fraud_ring)
        
        except Exception as e:
            logger.warning(f"Fraud ring detection failed: {e}")
        
        logger.info(f"Detected {len(fraud_rings)} potential fraud rings")
        return fraud_rings
    
    def _calculate_ring_risk_score(self, subgraph: nx.Graph, density: float, centrality: Dict[str, float]) -> float:
        """Calculate risk score for a potential fraud ring"""
        # Base score from density
        score = density * 0.4
        
        # Add score from centralization
        centrality_values = list(centrality.values())
        centralization = max(centrality_values) - np.mean(centrality_values)
        score += centralization * 0.3
        
        # Add score from size (larger rings are more suspicious)
        size_factor = min(1.0, len(subgraph.nodes()) / 10.0)
        score += size_factor * 0.2
        
        # Add score from edge attributes (if available)
        edge_score = 0
        for edge in subgraph.edges(data=True):
            edge_data = edge[2]
            if edge_data.get("relationship_type") in ["SHARED_ADDRESS", "SHARED_PROVIDER", "SHARED_PHONE"]:
                edge_score += 0.1
        
        score += min(0.1, edge_score)
        
        return min(1.0, score)
    
    async def _collect_ring_evidence(self, subgraph: nx.Graph) -> List[Dict[str, Any]]:
        """Collect evidence for a fraud ring"""
        evidence = []
        
        # Shared attributes evidence
        shared_attributes = {}
        for node in subgraph.nodes():
            node_data = subgraph.nodes[node]
            props = node_data.get("properties", {})
            
            for attr in ["address", "phone", "provider", "bank_account"]:
                if attr in props:
                    if attr not in shared_attributes:
                        shared_attributes[attr] = {}
                    
                    value = props[attr]
                    if value not in shared_attributes[attr]:
                        shared_attributes[attr][value] = []
                    shared_attributes[attr][value].append(node)
        
        # Find shared values
        for attr, values in shared_attributes.items():
            for value, nodes in values.items():
                if len(nodes) >= 2:
                    evidence.append({
                        "type": f"SHARED_{attr.upper()}",
                        "value": value,
                        "entities": nodes,
                        "strength": len(nodes) / len(subgraph.nodes())
                    })
        
        # Temporal evidence
        timestamps = []
        for node in subgraph.nodes():
            node_data = subgraph.nodes[node]
            props = node_data.get("properties", {})
            
            if "incident_date" in props:
                try:
                    timestamp = datetime.fromisoformat(props["incident_date"].replace('Z', '+00:00'))
                    timestamps.append(timestamp)
                except:
                    continue
        
        if len(timestamps) >= 2:
            time_span = max(timestamps) - min(timestamps)
            if time_span.days <= 30:  # Within 30 days
                evidence.append({
                    "type": "TEMPORAL_PROXIMITY",
                    "time_span_days": time_span.days,
                    "strength": max(0, 1.0 - time_span.days / 30.0)
                })
        
        return evidence
    
    async def _calculate_centrality_scores(self, graph: nx.Graph) -> Dict[str, float]:
        """Calculate various centrality scores"""
        centrality_scores = {}
        
        try:
            # Degree centrality
            degree_centrality = nx.degree_centrality(graph)
            
            # Betweenness centrality
            betweenness_centrality = nx.betweenness_centrality(graph)
            
            # Closeness centrality
            closeness_centrality = nx.closeness_centrality(graph)
            
            # Combine scores
            for node in graph.nodes():
                combined_score = (
                    degree_centrality.get(node, 0) * 0.4 +
                    betweenness_centrality.get(node, 0) * 0.3 +
                    closeness_centrality.get(node, 0) * 0.3
                )
                centrality_scores[node] = combined_score
        
        except Exception as e:
            logger.warning(f"Centrality calculation failed: {e}")
            # Fallback to degree centrality only
            centrality_scores = nx.degree_centrality(graph)
        
        return centrality_scores
    
    async def _calculate_network_risk_score(self, patterns: List[Dict], rings: List[FraudRing], centrality: Dict[str, float]) -> float:
        """Calculate overall network risk score"""
        score = 0.0
        
        # Score from suspicious patterns
        pattern_score = sum(pattern.get("score", 0) for pattern in patterns) / max(1, len(patterns))
        score += pattern_score * 0.4
        
        # Score from fraud rings
        if rings:
            ring_score = max(ring.risk_score for ring in rings)
            score += ring_score * 0.4
        
        # Score from centrality (high centrality can indicate key fraud actors)
        if centrality:
            max_centrality = max(centrality.values())
            score += max_centrality * 0.2
        
        return min(1.0, score)
    
    async def _cache_analysis_result(self, analysis_id: str, result: NetworkAnalysisResult):
        """Cache analysis result in Redis"""
        try:
            result_dict = asdict(result)
            # Convert datetime to string for JSON serialization
            result_dict["analysis_time"] = result.analysis_time.isoformat()
            for ring in result_dict["fraud_rings"]:
                ring["detection_time"] = ring["detection_time"].isoformat() if isinstance(ring["detection_time"], datetime) else ring["detection_time"]
            
            self.redis_client.setex(
                f"analysis:{analysis_id}",
                3600,  # 1 hour TTL
                json.dumps(result_dict)
            )
        except Exception as e:
            logger.warning(f"Failed to cache analysis result: {e}")
    
    async def get_cached_analysis(self, analysis_id: str) -> Optional[NetworkAnalysisResult]:
        """Get cached analysis result"""
        try:
            cached_data = self.redis_client.get(f"analysis:{analysis_id}")
            if cached_data:
                result_dict = json.loads(cached_data)
                # Convert string back to datetime
                result_dict["analysis_time"] = datetime.fromisoformat(result_dict["analysis_time"])
                for ring in result_dict["fraud_rings"]:
                    ring["detection_time"] = datetime.fromisoformat(ring["detection_time"])
                
                return NetworkAnalysisResult(**result_dict)
        except Exception as e:
            logger.warning(f"Failed to get cached analysis: {e}")
        
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for the service"""
        try:
            # Test Neo4j connection
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                neo4j_healthy = result.single()["test"] == 1
            
            # Test Redis connection
            redis_healthy = self.redis_client.ping()
            
            return {
                "status": "healthy" if neo4j_healthy and redis_healthy else "unhealthy",
                "neo4j": "connected" if neo4j_healthy else "disconnected",
                "redis": "connected" if redis_healthy else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

# HTTP API handlers
async def analyze_network_handler(request):
    """HTTP handler for network analysis"""
    try:
        data = await request.json()
        claim_id = data.get("claim_id")
        analysis_depth = data.get("depth", 3)
        
        if not claim_id:
            return web.json_response({"error": "claim_id is required"}, status=400)
        
        analyzer = request.app["analyzer"]
        result = await analyzer.analyze_claim_network(claim_id, analysis_depth)
        
        # Convert result to dict for JSON response
        result_dict = asdict(result)
        result_dict["analysis_time"] = result.analysis_time.isoformat()
        for ring in result_dict["fraud_rings"]:
            ring["detection_time"] = ring["detection_time"].isoformat()
        
        return web.json_response(result_dict)
    
    except Exception as e:
        logger.error(f"Network analysis failed: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def get_analysis_handler(request):
    """HTTP handler to get cached analysis"""
    try:
        analysis_id = request.match_info["analysis_id"]
        
        analyzer = request.app["analyzer"]
        result = await analyzer.get_cached_analysis(analysis_id)
        
        if not result:
            return web.json_response({"error": "Analysis not found"}, status=404)
        
        # Convert result to dict for JSON response
        result_dict = asdict(result)
        result_dict["analysis_time"] = result.analysis_time.isoformat()
        for ring in result_dict["fraud_rings"]:
            ring["detection_time"] = ring["detection_time"].isoformat()
        
        return web.json_response(result_dict)
    
    except Exception as e:
        logger.error(f"Get analysis failed: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def health_handler(request):
    """HTTP handler for health check"""
    analyzer = request.app["analyzer"]
    health_status = await analyzer.health_check()
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return web.json_response(health_status, status=status_code)

async def init_app():
    """Initialize the web application"""
    app = web.Application()
    
    # Initialize graph analyzer
    analyzer = GraphAnalyzer()
    app["analyzer"] = analyzer
    
    # Setup routes
    app.router.add_post("/api/v1/network-analysis", analyze_network_handler)
    app.router.add_get("/api/v1/analysis/{analysis_id}", get_analysis_handler)
    app.router.add_get("/health", health_handler)
    
    return app

def main():
    """Main function"""
    # Start Prometheus metrics server
    start_http_server(8001)
    
    # Create and run the web application
    app = init_app()
    
    port = int(os.getenv("PORT", 8523))
    logger.info(f"Starting Graph Analyzer service on port {port}")
    
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
