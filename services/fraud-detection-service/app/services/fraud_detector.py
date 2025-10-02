"""
Fraud Detection Service

Core fraud detection logic with ML model integration and real-time scoring.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import structlog
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.infrastructure.database import DatabaseManager
from app.infrastructure.cache import CacheManager
from app.services.model_manager import ModelManager
from app.domain.fraud_models import (
    FraudAssessmentRequest,
    FraudAssessmentResponse,
    FraudScore,
    RiskLevel,
    FraudRule,
    TransactionFeatures
)

logger = structlog.get_logger(__name__)

class FraudDetectionService:
    """
    Core fraud detection service that combines rule-based and ML-based detection.
    """
    
    def __init__(
        self,
        database_manager: DatabaseManager,
        cache_manager: CacheManager,
        model_manager: ModelManager,
        settings: Settings
    ):
        self.database_manager = database_manager
        self.cache_manager = cache_manager
        self.model_manager = model_manager
        self.settings = settings
        
        # Fraud detection configuration
        self.fraud_threshold = settings.fraud_threshold
        self.high_risk_threshold = settings.high_risk_threshold
        self.cache_ttl = settings.fraud_cache_ttl
        
        # Rule engine
        self.fraud_rules: List[FraudRule] = []
        
        # Performance metrics
        self.assessment_count = 0
        self.fraud_detected_count = 0
        self.last_model_update = None
        
    async def initialize(self):
        """Initialize the fraud detection service"""
        logger.info("Initializing Fraud Detection Service")
        
        # Load fraud rules
        await self._load_fraud_rules()
        
        # Warm up cache with common patterns
        await self._warm_up_cache()
        
        logger.info("Fraud Detection Service initialized successfully")
    
    async def assess_fraud_risk(
        self,
        request: FraudAssessmentRequest
    ) -> FraudAssessmentResponse:
        """
        Assess fraud risk for a transaction using both rules and ML models.
        """
        start_time = time.time()
        assessment_id = str(uuid4())
        
        try:
            logger.info(
                "Starting fraud assessment",
                assessment_id=assessment_id,
                transaction_id=request.transaction_id,
                amount=request.amount,
                user_id=request.user_id
            )
            
            # Check cache first
            cache_key = self._get_cache_key(request)
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                logger.info("Returning cached fraud assessment", assessment_id=assessment_id)
                return FraudAssessmentResponse.parse_obj(cached_result)
            
            # Extract features
            features = await self._extract_features(request)
            
            # Apply rule-based detection
            rule_results = await self._apply_fraud_rules(request, features)
            
            # Apply ML-based detection
            ml_score = await self._get_ml_fraud_score(features)
            
            # Combine scores
            final_score = self._combine_scores(rule_results, ml_score)
            
            # Determine risk level and decision
            risk_level = self._determine_risk_level(final_score)
            decision = self._make_fraud_decision(final_score, risk_level, rule_results)
            
            # Create response
            response = FraudAssessmentResponse(
                assessment_id=assessment_id,
                transaction_id=request.transaction_id,
                fraud_score=final_score,
                risk_level=risk_level,
                decision=decision,
                triggered_rules=[rule.rule_id for rule in rule_results if rule.triggered],
                ml_score=ml_score.score,
                features_used=list(features.dict().keys()),
                processing_time_ms=int((time.time() - start_time) * 1000),
                timestamp=datetime.utcnow()
            )
            
            # Cache the result
            await self.cache_manager.set(
                cache_key,
                response.dict(),
                ttl=self.cache_ttl
            )
            
            # Store assessment in database
            await self._store_assessment(response, features)
            
            # Update metrics
            self.assessment_count += 1
            if decision == "BLOCK":
                self.fraud_detected_count += 1
            
            logger.info(
                "Fraud assessment completed",
                assessment_id=assessment_id,
                fraud_score=final_score.score,
                risk_level=risk_level,
                decision=decision,
                processing_time_ms=response.processing_time_ms
            )
            
            return response
            
        except Exception as e:
            logger.error(
                "Error during fraud assessment",
                assessment_id=assessment_id,
                error=str(e),
                exc_info=True
            )
            
            # Return safe default response
            return FraudAssessmentResponse(
                assessment_id=assessment_id,
                transaction_id=request.transaction_id,
                fraud_score=FraudScore(score=0.5, confidence=0.0),
                risk_level=RiskLevel.MEDIUM,
                decision="REVIEW",
                triggered_rules=[],
                ml_score=0.5,
                features_used=[],
                processing_time_ms=int((time.time() - start_time) * 1000),
                timestamp=datetime.utcnow(),
                error_message=str(e)
            )
    
    async def _extract_features(
        self,
        request: FraudAssessmentRequest
    ) -> TransactionFeatures:
        """Extract features for fraud detection"""
        
        # Get user transaction history
        user_history = await self._get_user_transaction_history(
            request.user_id,
            days=30
        )
        
        # Get device/IP history
        device_history = await self._get_device_history(
            request.device_fingerprint,
            request.ip_address,
            days=7
        )
        
        # Calculate velocity features
        velocity_features = self._calculate_velocity_features(
            request,
            user_history
        )
        
        # Calculate behavioral features
        behavioral_features = self._calculate_behavioral_features(
            request,
            user_history
        )
        
        # Calculate network features
        network_features = self._calculate_network_features(
            request,
            device_history
        )
        
        return TransactionFeatures(
            # Basic transaction features
            amount=request.amount,
            currency=request.currency,
            transaction_type=request.transaction_type,
            merchant_category=request.merchant_category,
            
            # Time-based features
            hour_of_day=request.timestamp.hour,
            day_of_week=request.timestamp.weekday(),
            is_weekend=request.timestamp.weekday() >= 5,
            is_night_time=request.timestamp.hour < 6 or request.timestamp.hour > 22,
            
            # User features
            user_age_days=(datetime.utcnow() - request.user_created_at).days,
            user_transaction_count=len(user_history),
            
            # Velocity features
            **velocity_features,
            
            # Behavioral features
            **behavioral_features,
            
            # Network features
            **network_features,
            
            # Location features
            country=request.country,
            is_high_risk_country=request.country in self.settings.high_risk_countries,
            
            # Device features
            is_mobile=request.device_type == "mobile",
            is_new_device=device_history.get("is_new_device", True),
        )
    
    def _calculate_velocity_features(
        self,
        request: FraudAssessmentRequest,
        user_history: List[Dict]
    ) -> Dict[str, float]:
        """Calculate velocity-based features"""
        
        now = datetime.utcnow()
        
        # Transactions in different time windows
        txns_1h = [t for t in user_history if (now - t["timestamp"]).total_seconds() < 3600]
        txns_24h = [t for t in user_history if (now - t["timestamp"]).total_seconds() < 86400]
        txns_7d = [t for t in user_history if (now - t["timestamp"]).days < 7]
        
        # Amount-based velocity
        amount_1h = sum(t["amount"] for t in txns_1h)
        amount_24h = sum(t["amount"] for t in txns_24h)
        amount_7d = sum(t["amount"] for t in txns_7d)
        
        # Count-based velocity
        count_1h = len(txns_1h)
        count_24h = len(txns_24h)
        count_7d = len(txns_7d)
        
        # Average transaction amount
        avg_amount_7d = amount_7d / max(count_7d, 1)
        
        return {
            "velocity_amount_1h": amount_1h,
            "velocity_amount_24h": amount_24h,
            "velocity_amount_7d": amount_7d,
            "velocity_count_1h": count_1h,
            "velocity_count_24h": count_24h,
            "velocity_count_7d": count_7d,
            "avg_amount_7d": avg_amount_7d,
            "amount_vs_avg_ratio": request.amount / max(avg_amount_7d, 1),
        }
    
    def _calculate_behavioral_features(
        self,
        request: FraudAssessmentRequest,
        user_history: List[Dict]
    ) -> Dict[str, float]:
        """Calculate behavioral features"""
        
        if not user_history:
            return {
                "merchant_frequency": 0.0,
                "amount_deviation": 1.0,
                "time_deviation": 1.0,
                "location_deviation": 1.0,
            }
        
        # Merchant frequency
        merchant_counts = {}
        for txn in user_history:
            merchant = txn.get("merchant_id", "unknown")
            merchant_counts[merchant] = merchant_counts.get(merchant, 0) + 1
        
        merchant_frequency = merchant_counts.get(request.merchant_id, 0) / len(user_history)
        
        # Amount deviation
        amounts = [t["amount"] for t in user_history]
        avg_amount = np.mean(amounts)
        std_amount = np.std(amounts) if len(amounts) > 1 else avg_amount
        amount_deviation = abs(request.amount - avg_amount) / max(std_amount, 1)
        
        # Time pattern deviation
        hours = [t["timestamp"].hour for t in user_history]
        common_hour = max(set(hours), key=hours.count) if hours else 12
        time_deviation = abs(request.timestamp.hour - common_hour) / 12
        
        # Location deviation (simplified)
        countries = [t.get("country", "unknown") for t in user_history]
        common_country = max(set(countries), key=countries.count) if countries else "unknown"
        location_deviation = 0.0 if request.country == common_country else 1.0
        
        return {
            "merchant_frequency": merchant_frequency,
            "amount_deviation": min(amount_deviation, 5.0),  # Cap at 5
            "time_deviation": time_deviation,
            "location_deviation": location_deviation,
        }
    
    def _calculate_network_features(
        self,
        request: FraudAssessmentRequest,
        device_history: Dict
    ) -> Dict[str, float]:
        """Calculate network and device features"""
        
        return {
            "is_vpn": device_history.get("is_vpn", False),
            "is_proxy": device_history.get("is_proxy", False),
            "is_tor": device_history.get("is_tor", False),
            "device_risk_score": device_history.get("risk_score", 0.5),
            "ip_reputation_score": device_history.get("ip_reputation", 0.5),
        }
    
    async def _apply_fraud_rules(
        self,
        request: FraudAssessmentRequest,
        features: TransactionFeatures
    ) -> List[FraudRule]:
        """Apply rule-based fraud detection"""
        
        triggered_rules = []
        
        for rule in self.fraud_rules:
            try:
                if await self._evaluate_rule(rule, request, features):
                    rule.triggered = True
                    rule.trigger_count += 1
                    triggered_rules.append(rule)
                    
                    logger.info(
                        "Fraud rule triggered",
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        transaction_id=request.transaction_id
                    )
            except Exception as e:
                logger.error(
                    "Error evaluating fraud rule",
                    rule_id=rule.rule_id,
                    error=str(e)
                )
        
        return triggered_rules
    
    async def _evaluate_rule(
        self,
        rule: FraudRule,
        request: FraudAssessmentRequest,
        features: TransactionFeatures
    ) -> bool:
        """Evaluate a single fraud rule"""
        
        # This is a simplified rule evaluation
        # In production, you'd have a more sophisticated rule engine
        
        if rule.rule_id == "high_amount":
            return request.amount > rule.threshold
        
        elif rule.rule_id == "velocity_amount_1h":
            return features.velocity_amount_1h > rule.threshold
        
        elif rule.rule_id == "velocity_count_1h":
            return features.velocity_count_1h > rule.threshold
        
        elif rule.rule_id == "high_risk_country":
            return features.is_high_risk_country
        
        elif rule.rule_id == "night_transaction":
            return features.is_night_time and request.amount > 1000
        
        elif rule.rule_id == "new_device_high_amount":
            return features.is_new_device and request.amount > 500
        
        elif rule.rule_id == "amount_deviation":
            return features.amount_deviation > rule.threshold
        
        return False
    
    async def _get_ml_fraud_score(
        self,
        features: TransactionFeatures
    ) -> FraudScore:
        """Get ML-based fraud score"""
        
        try:
            # Get the current model
            model = await self.model_manager.get_current_model()
            if not model:
                logger.warning("No ML model available, using default score")
                return FraudScore(score=0.5, confidence=0.0)
            
            # Prepare features for model
            feature_vector = self._prepare_features_for_model(features)
            
            # Get prediction
            fraud_probability = model.predict_proba([feature_vector])[0][1]
            confidence = max(model.predict_proba([feature_vector])[0]) - 0.5
            
            return FraudScore(
                score=float(fraud_probability),
                confidence=float(confidence)
            )
            
        except Exception as e:
            logger.error("Error getting ML fraud score", error=str(e))
            return FraudScore(score=0.5, confidence=0.0)
    
    def _prepare_features_for_model(
        self,
        features: TransactionFeatures
    ) -> List[float]:
        """Prepare features for ML model input"""
        
        # This should match your model's expected feature format
        return [
            features.amount,
            features.hour_of_day,
            features.day_of_week,
            float(features.is_weekend),
            float(features.is_night_time),
            features.user_age_days,
            features.user_transaction_count,
            features.velocity_amount_1h,
            features.velocity_amount_24h,
            features.velocity_count_1h,
            features.velocity_count_24h,
            features.amount_deviation,
            features.time_deviation,
            features.location_deviation,
            float(features.is_high_risk_country),
            float(features.is_mobile),
            float(features.is_new_device),
        ]
    
    def _combine_scores(
        self,
        rule_results: List[FraudRule],
        ml_score: FraudScore
    ) -> FraudScore:
        """Combine rule-based and ML-based scores"""
        
        # Calculate rule-based score
        rule_score = 0.0
        max_rule_weight = 0.0
        
        for rule in rule_results:
            if rule.triggered:
                rule_score += rule.weight
                max_rule_weight = max(max_rule_weight, rule.weight)
        
        # Normalize rule score
        rule_score = min(rule_score, 1.0)
        
        # Combine scores (weighted average)
        rule_weight = 0.3
        ml_weight = 0.7
        
        combined_score = (rule_weight * rule_score) + (ml_weight * ml_score.score)
        combined_confidence = ml_score.confidence
        
        return FraudScore(
            score=combined_score,
            confidence=combined_confidence
        )
    
    def _determine_risk_level(self, fraud_score: FraudScore) -> RiskLevel:
        """Determine risk level based on fraud score"""
        
        if fraud_score.score >= self.fraud_threshold:
            return RiskLevel.HIGH
        elif fraud_score.score >= self.high_risk_threshold:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _make_fraud_decision(
        self,
        fraud_score: FraudScore,
        risk_level: RiskLevel,
        rule_results: List[FraudRule]
    ) -> str:
        """Make final fraud decision"""
        
        # Check for critical rules
        critical_rules_triggered = any(
            rule.triggered and rule.severity == "CRITICAL"
            for rule in rule_results
        )
        
        if critical_rules_triggered:
            return "BLOCK"
        
        if risk_level == RiskLevel.HIGH:
            return "BLOCK"
        elif risk_level == RiskLevel.MEDIUM:
            return "REVIEW"
        else:
            return "ALLOW"
    
    async def _load_fraud_rules(self):
        """Load fraud detection rules"""
        
        # In production, these would be loaded from database
        self.fraud_rules = [
            FraudRule(
                rule_id="high_amount",
                name="High Amount Transaction",
                description="Transaction amount exceeds threshold",
                threshold=10000.0,
                weight=0.8,
                severity="HIGH"
            ),
            FraudRule(
                rule_id="velocity_amount_1h",
                name="High Amount Velocity (1h)",
                description="High transaction amount in 1 hour",
                threshold=5000.0,
                weight=0.7,
                severity="HIGH"
            ),
            FraudRule(
                rule_id="velocity_count_1h",
                name="High Transaction Count (1h)",
                description="High transaction count in 1 hour",
                threshold=10.0,
                weight=0.6,
                severity="MEDIUM"
            ),
            FraudRule(
                rule_id="high_risk_country",
                name="High Risk Country",
                description="Transaction from high risk country",
                threshold=0.0,
                weight=0.5,
                severity="MEDIUM"
            ),
            FraudRule(
                rule_id="night_transaction",
                name="Night Time High Amount",
                description="High amount transaction at night",
                threshold=0.0,
                weight=0.4,
                severity="MEDIUM"
            ),
            FraudRule(
                rule_id="new_device_high_amount",
                name="New Device High Amount",
                description="High amount from new device",
                threshold=0.0,
                weight=0.6,
                severity="HIGH"
            ),
            FraudRule(
                rule_id="amount_deviation",
                name="Amount Deviation",
                description="Transaction amount deviates from user pattern",
                threshold=3.0,
                weight=0.3,
                severity="LOW"
            ),
        ]
        
        logger.info("Loaded fraud rules", count=len(self.fraud_rules))
    
    async def _warm_up_cache(self):
        """Warm up cache with common patterns"""
        logger.info("Warming up fraud detection cache")
        # Implementation would pre-load common user patterns, etc.
    
    def _get_cache_key(self, request: FraudAssessmentRequest) -> str:
        """Generate cache key for fraud assessment"""
        return f"fraud_assessment:{request.user_id}:{request.amount}:{request.merchant_id}"
    
    async def _get_user_transaction_history(
        self,
        user_id: str,
        days: int = 30
    ) -> List[Dict]:
        """Get user transaction history"""
        # Implementation would query database
        return []
    
    async def _get_device_history(
        self,
        device_fingerprint: Optional[str],
        ip_address: str,
        days: int = 7
    ) -> Dict:
        """Get device/IP history"""
        # Implementation would query device intelligence service
        return {
            "is_new_device": True,
            "is_vpn": False,
            "is_proxy": False,
            "is_tor": False,
            "risk_score": 0.2,
            "ip_reputation": 0.8,
        }
    
    async def _store_assessment(
        self,
        response: FraudAssessmentResponse,
        features: TransactionFeatures
    ):
        """Store fraud assessment in database"""
        # Implementation would store assessment for audit and model training
        pass
    
    async def get_fraud_statistics(self) -> Dict[str, Any]:
        """Get fraud detection statistics"""
        return {
            "total_assessments": self.assessment_count,
            "fraud_detected": self.fraud_detected_count,
            "fraud_rate": self.fraud_detected_count / max(self.assessment_count, 1),
            "last_model_update": self.last_model_update,
            "active_rules": len(self.fraud_rules),
        }
