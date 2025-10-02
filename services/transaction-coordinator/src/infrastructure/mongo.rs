use async_trait::async_trait;
use mongodb::{
    bson::{doc, Document},
    options::{ClientOptions, FindOptions, UpdateOptions},
    Client, Collection, Database,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::domain::{Transaction, Saga, OutboxEvent, OutboxEventFilter, OutboxEventStatus};

pub struct MongoRepository {
    database: Database,
    transactions: Collection<Transaction>,
    sagas: Collection<Saga>,
    outbox_events: Collection<OutboxEvent>,
}

impl MongoRepository {
    pub async fn new(connection_string: &str) -> anyhow::Result<Self> {
        let client_options = ClientOptions::parse(connection_string).await?;
        let client = Client::with_options(client_options)?;
        let database = client.database("transaction_coordinator");

        let transactions = database.collection::<Transaction>("transactions");
        let sagas = database.collection::<Saga>("sagas");
        let outbox_events = database.collection::<OutboxEvent>("outbox_events");

        // Create indexes
        let _ = transactions
            .create_index(doc! { "id": 1 }, None)
            .await;
        let _ = transactions
            .create_index(doc! { "status": 1, "created_at": 1 }, None)
            .await;

        let _ = sagas
            .create_index(doc! { "id": 1 }, None)
            .await;
        let _ = sagas
            .create_index(doc! { "status": 1, "created_at": 1 }, None)
            .await;

        let _ = outbox_events
            .create_index(doc! { "id": 1 }, None)
            .await;
        let _ = outbox_events
            .create_index(doc! { "status": 1, "created_at": 1 }, None)
            .await;
        let _ = outbox_events
            .create_index(doc! { "aggregate_id": 1, "aggregate_type": 1 }, None)
            .await;

        Ok(Self {
            database,
            transactions,
            sagas,
            outbox_events,
        })
    }

    // Transaction methods
    pub async fn save_transaction(&self, transaction: &Transaction) -> anyhow::Result<()> {
        let options = UpdateOptions::builder().upsert(true).build();
        self.transactions
            .replace_one(doc! { "id": transaction.id.to_string() }, transaction, options)
            .await?;
        Ok(())
    }

    pub async fn get_transaction(&self, id: Uuid) -> anyhow::Result<Option<Transaction>> {
        let result = self
            .transactions
            .find_one(doc! { "id": id.to_string() }, None)
            .await?;
        Ok(result)
    }

    pub async fn get_transactions_by_status(&self, status: &str) -> anyhow::Result<Vec<Transaction>> {
        let cursor = self
            .transactions
            .find(doc! { "status": status }, None)
            .await?;
        
        let mut transactions = Vec::new();
        let mut cursor = cursor;
        while cursor.advance().await? {
            transactions.push(cursor.deserialize_current()?);
        }
        Ok(transactions)
    }

    // Saga methods
    pub async fn save_saga(&self, saga: &Saga) -> anyhow::Result<()> {
        let options = UpdateOptions::builder().upsert(true).build();
        self.sagas
            .replace_one(doc! { "id": saga.id.to_string() }, saga, options)
            .await?;
        Ok(())
    }

    pub async fn get_saga(&self, id: Uuid) -> anyhow::Result<Option<Saga>> {
        let result = self
            .sagas
            .find_one(doc! { "id": id.to_string() }, None)
            .await?;
        Ok(result)
    }

    pub async fn get_sagas_by_status(&self, status: &str) -> anyhow::Result<Vec<Saga>> {
        let cursor = self
            .sagas
            .find(doc! { "status": status }, None)
            .await?;
        
        let mut sagas = Vec::new();
        let mut cursor = cursor;
        while cursor.advance().await? {
            sagas.push(cursor.deserialize_current()?);
        }
        Ok(sagas)
    }

    // Outbox methods
    pub async fn save_outbox_event(&self, event: &OutboxEvent) -> anyhow::Result<()> {
        let options = UpdateOptions::builder().upsert(true).build();
        self.outbox_events
            .replace_one(doc! { "id": event.id.to_string() }, event, options)
            .await?;
        Ok(())
    }

    pub async fn get_outbox_event(&self, id: Uuid) -> anyhow::Result<Option<OutboxEvent>> {
        let result = self
            .outbox_events
            .find_one(doc! { "id": id.to_string() }, None)
            .await?;
        Ok(result)
    }

    pub async fn get_pending_outbox_events(&self, limit: u32) -> anyhow::Result<Vec<OutboxEvent>> {
        let options = FindOptions::builder()
            .limit(limit as i64)
            .sort(doc! { "created_at": 1 })
            .build();

        let cursor = self
            .outbox_events
            .find(doc! { "status": "Pending" }, options)
            .await?;
        
        let mut events = Vec::new();
        let mut cursor = cursor;
        while cursor.advance().await? {
            events.push(cursor.deserialize_current()?);
        }
        Ok(events)
    }

    pub async fn get_failed_outbox_events(&self, limit: u32) -> anyhow::Result<Vec<OutboxEvent>> {
        let now = chrono::Utc::now();
        let options = FindOptions::builder()
            .limit(limit as i64)
            .sort(doc! { "next_retry_at": 1 })
            .build();

        let cursor = self
            .outbox_events
            .find(
                doc! { 
                    "status": "Failed",
                    "next_retry_at": { "$lte": now }
                },
                options,
            )
            .await?;
        
        let mut events = Vec::new();
        let mut cursor = cursor;
        while cursor.advance().await? {
            events.push(cursor.deserialize_current()?);
        }
        Ok(events)
    }

    pub async fn get_outbox_events_by_filter(&self, filter: &OutboxEventFilter) -> anyhow::Result<Vec<OutboxEvent>> {
        let mut query = Document::new();

        if let Some(aggregate_type) = &filter.aggregate_type {
            query.insert("aggregate_type", aggregate_type);
        }

        if let Some(event_type) = &filter.event_type {
            query.insert("event_type", event_type);
        }

        if let Some(status) = &filter.status {
            query.insert("status", format!("{:?}", status));
        }

        if let Some(created_after) = filter.created_after {
            query.insert("created_at", doc! { "$gte": created_after });
        }

        if let Some(created_before) = filter.created_before {
            let existing_created_at = query.get("created_at").cloned();
            if let Some(existing) = existing_created_at {
                if let Ok(mut existing_doc) = existing.as_document().cloned() {
                    existing_doc.insert("$lte", created_before);
                    query.insert("created_at", existing_doc);
                }
            } else {
                query.insert("created_at", doc! { "$lte": created_before });
            }
        }

        let options = FindOptions::builder()
            .limit(filter.limit.unwrap_or(100) as i64)
            .sort(doc! { "created_at": -1 })
            .build();

        let cursor = self.outbox_events.find(query, options).await?;
        
        let mut events = Vec::new();
        let mut cursor = cursor;
        while cursor.advance().await? {
            events.push(cursor.deserialize_current()?);
        }
        Ok(events)
    }

    pub async fn delete_processed_outbox_events(&self, older_than_hours: u32) -> anyhow::Result<u64> {
        let cutoff_time = chrono::Utc::now() - chrono::Duration::hours(older_than_hours as i64);
        
        let result = self
            .outbox_events
            .delete_many(
                doc! {
                    "status": "Processed",
                    "processed_at": { "$lt": cutoff_time }
                },
                None,
            )
            .await?;

        Ok(result.deleted_count)
    }

    // Transaction operations with outbox pattern
    pub async fn save_transaction_with_events(&self, transaction: &Transaction, events: Vec<OutboxEvent>) -> anyhow::Result<()> {
        let mut session = self.database.client().start_session(None).await?;
        session.start_transaction(None).await?;

        // Save transaction
        let options = UpdateOptions::builder().upsert(true).build();
        self.transactions
            .replace_one_with_session(
                doc! { "id": transaction.id.to_string() },
                transaction,
                options,
                &mut session,
            )
            .await?;

        // Save outbox events
        for event in events {
            let options = UpdateOptions::builder().upsert(true).build();
            self.outbox_events
                .replace_one_with_session(
                    doc! { "id": event.id.to_string() },
                    &event,
                    options,
                    &mut session,
                )
                .await?;
        }

        session.commit_transaction().await?;
        Ok(())
    }

    pub async fn save_saga_with_events(&self, saga: &Saga, events: Vec<OutboxEvent>) -> anyhow::Result<()> {
        let mut session = self.database.client().start_session(None).await?;
        session.start_transaction(None).await?;

        // Save saga
        let options = UpdateOptions::builder().upsert(true).build();
        self.sagas
            .replace_one_with_session(
                doc! { "id": saga.id.to_string() },
                saga,
                options,
                &mut session,
            )
            .await?;

        // Save outbox events
        for event in events {
            let options = UpdateOptions::builder().upsert(true).build();
            self.outbox_events
                .replace_one_with_session(
                    doc! { "id": event.id.to_string() },
                    &event,
                    options,
                    &mut session,
                )
                .await?;
        }

        session.commit_transaction().await?;
        Ok(())
    }
}
