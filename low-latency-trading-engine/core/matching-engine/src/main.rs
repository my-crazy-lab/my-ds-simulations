use std::collections::{BTreeMap, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};
use std::thread;
use std::sync::mpsc::{self, Receiver, Sender};

use serde::{Deserialize, Serialize};
use tokio::time::{Duration, Instant};
use uuid::Uuid;

// High-performance order and trade structures
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub order_id: String,
    pub client_id: String,
    pub symbol: String,
    pub side: OrderSide,
    pub order_type: OrderType,
    pub quantity: u64,
    pub price: Option<u64>, // Price in ticks (e.g., cents)
    pub time_in_force: TimeInForce,
    pub timestamp: u64, // Nanoseconds since epoch
    pub sequence_number: u64,
    pub remaining_quantity: u64,
    pub status: OrderStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OrderSide {
    Buy,
    Sell,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OrderType {
    Market,
    Limit,
    Stop,
    StopLimit,
    Iceberg { visible_quantity: u64 },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TimeInForce {
    GTC, // Good Till Cancel
    IOC, // Immediate Or Cancel
    FOK, // Fill Or Kill
    GTD { expire_time: u64 }, // Good Till Date
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OrderStatus {
    New,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
    Expired,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trade {
    pub trade_id: String,
    pub symbol: String,
    pub buy_order_id: String,
    pub sell_order_id: String,
    pub buy_client_id: String,
    pub sell_client_id: String,
    pub quantity: u64,
    pub price: u64,
    pub timestamp: u64,
    pub sequence_number: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketData {
    pub symbol: String,
    pub timestamp: u64,
    pub sequence_number: u64,
    pub best_bid: Option<u64>,
    pub best_ask: Option<u64>,
    pub bid_size: u64,
    pub ask_size: u64,
    pub last_trade_price: Option<u64>,
    pub last_trade_quantity: u64,
    pub total_volume: u64,
}

// Lock-free order book implementation
pub struct OrderBook {
    symbol: String,
    buy_orders: BTreeMap<u64, VecDeque<Order>>, // Price -> Orders (descending for buys)
    sell_orders: BTreeMap<u64, VecDeque<Order>>, // Price -> Orders (ascending for sells)
    sequence_counter: AtomicU64,
    total_volume: AtomicU64,
    last_trade_price: AtomicU64,
    last_trade_quantity: AtomicU64,
}

impl OrderBook {
    pub fn new(symbol: String) -> Self {
        Self {
            symbol,
            buy_orders: BTreeMap::new(),
            sell_orders: BTreeMap::new(),
            sequence_counter: AtomicU64::new(0),
            total_volume: AtomicU64::new(0),
            last_trade_price: AtomicU64::new(0),
            last_trade_quantity: AtomicU64::new(0),
        }
    }

    pub fn add_order(&mut self, mut order: Order) -> Vec<Trade> {
        let mut trades = Vec::new();
        let start_time = get_nanosecond_timestamp();
        
        order.sequence_number = self.sequence_counter.fetch_add(1, Ordering::SeqCst);
        order.timestamp = start_time;
        order.remaining_quantity = order.quantity;
        order.status = OrderStatus::New;

        // Handle market orders and aggressive limit orders
        if order.order_type == OrderType::Market || self.can_match_immediately(&order) {
            trades = self.match_order(&mut order);
        }

        // Add remaining quantity to order book if not fully filled
        if order.remaining_quantity > 0 && order.status != OrderStatus::Cancelled {
            self.add_to_book(order);
        }

        trades
    }

    fn can_match_immediately(&self, order: &Order) -> bool {
        match (&order.side, &order.order_type) {
            (OrderSide::Buy, OrderType::Limit) => {
                if let Some(price) = order.price {
                    if let Some((&best_ask, _)) = self.sell_orders.iter().next() {
                        return price >= best_ask;
                    }
                }
            }
            (OrderSide::Sell, OrderType::Limit) => {
                if let Some(price) = order.price {
                    if let Some((&best_bid, _)) = self.buy_orders.iter().next_back() {
                        return price <= best_bid;
                    }
                }
            }
            _ => {}
        }
        false
    }

    fn match_order(&mut self, order: &mut Order) -> Vec<Trade> {
        let mut trades = Vec::new();
        
        match order.side {
            OrderSide::Buy => {
                // Match against sell orders (ascending price order)
                let mut prices_to_remove = Vec::new();
                
                for (&price, sell_queue) in self.sell_orders.iter_mut() {
                    if order.remaining_quantity == 0 {
                        break;
                    }
                    
                    // Check if we can match at this price
                    if let Some(order_price) = order.price {
                        if order.order_type == OrderType::Limit && price > order_price {
                            break;
                        }
                    }
                    
                    while let Some(mut sell_order) = sell_queue.pop_front() {
                        if order.remaining_quantity == 0 {
                            sell_queue.push_front(sell_order);
                            break;
                        }
                        
                        let trade_quantity = std::cmp::min(order.remaining_quantity, sell_order.remaining_quantity);
                        let trade_price = price; // Price improvement for aggressive order
                        
                        // Create trade
                        let trade = Trade {
                            trade_id: Uuid::new_v4().simple().to_string(),
                            symbol: self.symbol.clone(),
                            buy_order_id: order.order_id.clone(),
                            sell_order_id: sell_order.order_id.clone(),
                            buy_client_id: order.client_id.clone(),
                            sell_client_id: sell_order.client_id.clone(),
                            quantity: trade_quantity,
                            price: trade_price,
                            timestamp: get_nanosecond_timestamp(),
                            sequence_number: self.sequence_counter.fetch_add(1, Ordering::SeqCst),
                        };
                        
                        // Update order quantities
                        order.remaining_quantity -= trade_quantity;
                        sell_order.remaining_quantity -= trade_quantity;
                        
                        // Update order statuses
                        if order.remaining_quantity == 0 {
                            order.status = OrderStatus::Filled;
                        } else {
                            order.status = OrderStatus::PartiallyFilled;
                        }
                        
                        if sell_order.remaining_quantity == 0 {
                            sell_order.status = OrderStatus::Filled;
                        } else {
                            sell_order.status = OrderStatus::PartiallyFilled;
                            sell_queue.push_front(sell_order);
                        }
                        
                        // Update market data
                        self.last_trade_price.store(trade_price, Ordering::SeqCst);
                        self.last_trade_quantity.store(trade_quantity, Ordering::SeqCst);
                        self.total_volume.fetch_add(trade_quantity, Ordering::SeqCst);
                        
                        trades.push(trade);
                        
                        if sell_order.remaining_quantity == 0 {
                            break;
                        }
                    }
                    
                    if sell_queue.is_empty() {
                        prices_to_remove.push(price);
                    }
                }
                
                // Remove empty price levels
                for price in prices_to_remove {
                    self.sell_orders.remove(&price);
                }
            }
            OrderSide::Sell => {
                // Match against buy orders (descending price order)
                let mut prices_to_remove = Vec::new();
                
                for (&price, buy_queue) in self.buy_orders.iter_mut().rev() {
                    if order.remaining_quantity == 0 {
                        break;
                    }
                    
                    // Check if we can match at this price
                    if let Some(order_price) = order.price {
                        if order.order_type == OrderType::Limit && price < order_price {
                            break;
                        }
                    }
                    
                    while let Some(mut buy_order) = buy_queue.pop_front() {
                        if order.remaining_quantity == 0 {
                            buy_queue.push_front(buy_order);
                            break;
                        }
                        
                        let trade_quantity = std::cmp::min(order.remaining_quantity, buy_order.remaining_quantity);
                        let trade_price = price; // Price improvement for aggressive order
                        
                        // Create trade
                        let trade = Trade {
                            trade_id: Uuid::new_v4().simple().to_string(),
                            symbol: self.symbol.clone(),
                            buy_order_id: buy_order.order_id.clone(),
                            sell_order_id: order.order_id.clone(),
                            buy_client_id: buy_order.client_id.clone(),
                            sell_client_id: order.client_id.clone(),
                            quantity: trade_quantity,
                            price: trade_price,
                            timestamp: get_nanosecond_timestamp(),
                            sequence_number: self.sequence_counter.fetch_add(1, Ordering::SeqCst),
                        };
                        
                        // Update order quantities
                        order.remaining_quantity -= trade_quantity;
                        buy_order.remaining_quantity -= trade_quantity;
                        
                        // Update order statuses
                        if order.remaining_quantity == 0 {
                            order.status = OrderStatus::Filled;
                        } else {
                            order.status = OrderStatus::PartiallyFilled;
                        }
                        
                        if buy_order.remaining_quantity == 0 {
                            buy_order.status = OrderStatus::Filled;
                        } else {
                            buy_order.status = OrderStatus::PartiallyFilled;
                            buy_queue.push_front(buy_order);
                        }
                        
                        // Update market data
                        self.last_trade_price.store(trade_price, Ordering::SeqCst);
                        self.last_trade_quantity.store(trade_quantity, Ordering::SeqCst);
                        self.total_volume.fetch_add(trade_quantity, Ordering::SeqCst);
                        
                        trades.push(trade);
                        
                        if buy_order.remaining_quantity == 0 {
                            break;
                        }
                    }
                    
                    if buy_queue.is_empty() {
                        prices_to_remove.push(price);
                    }
                }
                
                // Remove empty price levels
                for price in prices_to_remove {
                    self.buy_orders.remove(&price);
                }
            }
        }
        
        trades
    }

    fn add_to_book(&mut self, order: Order) {
        if let Some(price) = order.price {
            match order.side {
                OrderSide::Buy => {
                    self.buy_orders.entry(price).or_insert_with(VecDeque::new).push_back(order);
                }
                OrderSide::Sell => {
                    self.sell_orders.entry(price).or_insert_with(VecDeque::new).push_back(order);
                }
            }
        }
    }

    pub fn get_market_data(&self) -> MarketData {
        let best_bid = self.buy_orders.keys().next_back().copied();
        let best_ask = self.sell_orders.keys().next().copied();
        
        let bid_size = best_bid
            .and_then(|price| self.buy_orders.get(&price))
            .map(|queue| queue.iter().map(|o| o.remaining_quantity).sum())
            .unwrap_or(0);
            
        let ask_size = best_ask
            .and_then(|price| self.sell_orders.get(&price))
            .map(|queue| queue.iter().map(|o| o.remaining_quantity).sum())
            .unwrap_or(0);

        MarketData {
            symbol: self.symbol.clone(),
            timestamp: get_nanosecond_timestamp(),
            sequence_number: self.sequence_counter.load(Ordering::SeqCst),
            best_bid,
            best_ask,
            bid_size,
            ask_size,
            last_trade_price: {
                let price = self.last_trade_price.load(Ordering::SeqCst);
                if price > 0 { Some(price) } else { None }
            },
            last_trade_quantity: self.last_trade_quantity.load(Ordering::SeqCst),
            total_volume: self.total_volume.load(Ordering::SeqCst),
        }
    }

    pub fn cancel_order(&mut self, order_id: &str) -> bool {
        // Search and remove order from buy side
        for (_, queue) in self.buy_orders.iter_mut() {
            if let Some(pos) = queue.iter().position(|o| o.order_id == order_id) {
                queue.remove(pos);
                return true;
            }
        }
        
        // Search and remove order from sell side
        for (_, queue) in self.sell_orders.iter_mut() {
            if let Some(pos) = queue.iter().position(|o| o.order_id == order_id) {
                queue.remove(pos);
                return true;
            }
        }
        
        false
    }
}

// High-performance matching engine
pub struct MatchingEngine {
    order_books: Arc<RwLock<std::collections::HashMap<String, OrderBook>>>,
    trade_sender: Sender<Trade>,
    market_data_sender: Sender<MarketData>,
    order_receiver: Receiver<Order>,
    cancel_receiver: Receiver<(String, String)>, // (symbol, order_id)
}

impl MatchingEngine {
    pub fn new(
        trade_sender: Sender<Trade>,
        market_data_sender: Sender<MarketData>,
        order_receiver: Receiver<Order>,
        cancel_receiver: Receiver<(String, String)>,
    ) -> Self {
        Self {
            order_books: Arc::new(RwLock::new(std::collections::HashMap::new())),
            trade_sender,
            market_data_sender,
            order_receiver,
            cancel_receiver,
        }
    }

    pub fn run(&mut self) {
        println!("Starting high-performance matching engine...");
        
        loop {
            // Process incoming orders with microsecond precision
            if let Ok(order) = self.order_receiver.try_recv() {
                let start_time = Instant::now();
                self.process_order(order);
                let processing_time = start_time.elapsed();
                
                if processing_time > Duration::from_micros(10) {
                    eprintln!("Warning: Order processing took {:?}", processing_time);
                }
            }
            
            // Process order cancellations
            if let Ok((symbol, order_id)) = self.cancel_receiver.try_recv() {
                self.process_cancellation(symbol, order_id);
            }
            
            // Yield CPU briefly to prevent 100% utilization
            thread::yield_now();
        }
    }

    fn process_order(&mut self, order: Order) {
        let symbol = order.symbol.clone();
        
        // Get or create order book
        let mut order_books = self.order_books.write().unwrap();
        let order_book = order_books.entry(symbol.clone()).or_insert_with(|| OrderBook::new(symbol.clone()));
        
        // Process order and generate trades
        let trades = order_book.add_order(order);
        
        // Send trades to trade capture
        for trade in trades {
            if let Err(e) = self.trade_sender.try_send(trade) {
                eprintln!("Failed to send trade: {}", e);
            }
        }
        
        // Send updated market data
        let market_data = order_book.get_market_data();
        if let Err(e) = self.market_data_sender.try_send(market_data) {
            eprintln!("Failed to send market data: {}", e);
        }
    }

    fn process_cancellation(&mut self, symbol: String, order_id: String) {
        let mut order_books = self.order_books.write().unwrap();
        if let Some(order_book) = order_books.get_mut(&symbol) {
            let cancelled = order_book.cancel_order(&order_id);
            if cancelled {
                // Send updated market data after cancellation
                let market_data = order_book.get_market_data();
                if let Err(e) = self.market_data_sender.try_send(market_data) {
                    eprintln!("Failed to send market data after cancellation: {}", e);
                }
            }
        }
    }
}

// Utility functions
fn get_nanosecond_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

// Main function for testing
#[tokio::main]
async fn main() {
    println!("Low-Latency Trading Engine - Matching Engine Core");
    
    // Create channels for communication
    let (trade_sender, trade_receiver) = mpsc::channel::<Trade>();
    let (market_data_sender, market_data_receiver) = mpsc::channel::<MarketData>();
    let (order_sender, order_receiver) = mpsc::channel::<Order>();
    let (cancel_sender, cancel_receiver) = mpsc::channel::<(String, String)>();
    
    // Start matching engine in separate thread
    let mut matching_engine = MatchingEngine::new(
        trade_sender,
        market_data_sender,
        order_receiver,
        cancel_receiver,
    );
    
    thread::spawn(move || {
        matching_engine.run();
    });
    
    // Example: Submit test orders
    let test_orders = vec![
        Order {
            order_id: "BUY001".to_string(),
            client_id: "CLIENT001".to_string(),
            symbol: "AAPL".to_string(),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            quantity: 1000,
            price: Some(15000), // $150.00 in cents
            time_in_force: TimeInForce::GTC,
            timestamp: 0,
            sequence_number: 0,
            remaining_quantity: 0,
            status: OrderStatus::New,
        },
        Order {
            order_id: "SELL001".to_string(),
            client_id: "CLIENT002".to_string(),
            symbol: "AAPL".to_string(),
            side: OrderSide::Sell,
            order_type: OrderType::Limit,
            quantity: 500,
            price: Some(15010), // $150.10 in cents
            time_in_force: TimeInForce::GTC,
            timestamp: 0,
            sequence_number: 0,
            remaining_quantity: 0,
            status: OrderStatus::New,
        },
        Order {
            order_id: "BUY002".to_string(),
            client_id: "CLIENT003".to_string(),
            symbol: "AAPL".to_string(),
            side: OrderSide::Buy,
            order_type: OrderType::Market,
            quantity: 200,
            price: None,
            time_in_force: TimeInForce::IOC,
            timestamp: 0,
            sequence_number: 0,
            remaining_quantity: 0,
            status: OrderStatus::New,
        },
    ];
    
    // Submit orders
    for order in test_orders {
        if let Err(e) = order_sender.send(order) {
            eprintln!("Failed to send order: {}", e);
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    
    // Monitor trades and market data
    tokio::spawn(async move {
        while let Ok(trade) = trade_receiver.recv() {
            println!("Trade executed: {} shares of {} at ${:.2}", 
                trade.quantity, trade.symbol, trade.price as f64 / 100.0);
        }
    });
    
    tokio::spawn(async move {
        while let Ok(market_data) = market_data_receiver.recv() {
            println!("Market Data - {}: Bid ${:.2} ({}) Ask ${:.2} ({})", 
                market_data.symbol,
                market_data.best_bid.unwrap_or(0) as f64 / 100.0,
                market_data.bid_size,
                market_data.best_ask.unwrap_or(0) as f64 / 100.0,
                market_data.ask_size);
        }
    });
    
    // Keep running
    tokio::time::sleep(Duration::from_secs(10)).await;
    println!("Matching engine test completed");
}
