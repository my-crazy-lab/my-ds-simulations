import { v4 as uuidv4 } from 'uuid';
import { BillingStatus, BillingType, PaymentStatus } from './types';
import { BillingCreatedEvent, BillingUpdatedEvent, InvoiceGeneratedEvent, PaymentProcessedEvent } from './events';

export interface BillingItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
  totalPrice: number;
  taxRate: number;
  taxAmount: number;
  metadata?: Record<string, any>;
}

export interface BillingAddress {
  street: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
}

export class BillingAggregate {
  public readonly id: string;
  public customerId: string;
  public orderId?: string;
  public transactionId?: string;
  public billingType: BillingType;
  public status: BillingStatus;
  public items: BillingItem[];
  public subtotal: number;
  public taxAmount: number;
  public discountAmount: number;
  public totalAmount: number;
  public currency: string;
  public billingAddress?: BillingAddress;
  public dueDate?: Date;
  public paidDate?: Date;
  public paymentStatus: PaymentStatus;
  public paymentMethod?: string;
  public paymentReference?: string;
  public notes?: string;
  public metadata: Record<string, any>;
  public createdAt: Date;
  public updatedAt: Date;
  public version: number;

  private uncommittedEvents: any[] = [];

  constructor(
    customerId: string,
    billingType: BillingType,
    items: BillingItem[],
    currency: string = 'USD',
    billingAddress?: BillingAddress,
    dueDate?: Date,
    metadata: Record<string, any> = {}
  ) {
    this.id = uuidv4();
    this.customerId = customerId;
    this.billingType = billingType;
    this.status = BillingStatus.DRAFT;
    this.items = items;
    this.currency = currency;
    this.billingAddress = billingAddress;
    this.dueDate = dueDate;
    this.paymentStatus = PaymentStatus.PENDING;
    this.metadata = metadata;
    this.createdAt = new Date();
    this.updatedAt = new Date();
    this.version = 0;

    // Calculate amounts
    this.calculateAmounts();

    // Add creation event
    this.addEvent(new BillingCreatedEvent(
      this.id,
      this.customerId,
      this.billingType,
      this.items,
      this.totalAmount,
      this.currency,
      this.createdAt
    ));
  }

  public static fromSnapshot(snapshot: any): BillingAggregate {
    const billing = Object.create(BillingAggregate.prototype);
    Object.assign(billing, snapshot);
    billing.uncommittedEvents = [];
    return billing;
  }

  public addItem(item: BillingItem): void {
    this.items.push(item);
    this.calculateAmounts();
    this.markUpdated();
  }

  public removeItem(itemId: string): void {
    this.items = this.items.filter(item => item.id !== itemId);
    this.calculateAmounts();
    this.markUpdated();
  }

  public updateItem(itemId: string, updates: Partial<BillingItem>): void {
    const itemIndex = this.items.findIndex(item => item.id === itemId);
    if (itemIndex === -1) {
      throw new Error(`Item with id ${itemId} not found`);
    }

    this.items[itemIndex] = { ...this.items[itemIndex], ...updates };
    
    // Recalculate item total if quantity or unit price changed
    if (updates.quantity !== undefined || updates.unitPrice !== undefined) {
      const item = this.items[itemIndex];
      item.totalPrice = item.quantity * item.unitPrice;
      item.taxAmount = item.totalPrice * item.taxRate;
    }

    this.calculateAmounts();
    this.markUpdated();
  }

  public applyDiscount(discountAmount: number, reason?: string): void {
    if (discountAmount < 0) {
      throw new Error('Discount amount cannot be negative');
    }

    this.discountAmount = discountAmount;
    this.calculateAmounts();
    this.markUpdated();

    if (reason) {
      this.metadata.discountReason = reason;
    }
  }

  public finalize(): void {
    if (this.status !== BillingStatus.DRAFT) {
      throw new Error('Only draft billing records can be finalized');
    }

    if (this.items.length === 0) {
      throw new Error('Cannot finalize billing record without items');
    }

    this.status = BillingStatus.FINALIZED;
    this.markUpdated();

    this.addEvent(new BillingUpdatedEvent(
      this.id,
      this.status,
      this.totalAmount,
      this.updatedAt
    ));
  }

  public generateInvoice(invoiceNumber: string): void {
    if (this.status !== BillingStatus.FINALIZED) {
      throw new Error('Billing record must be finalized before generating invoice');
    }

    this.status = BillingStatus.INVOICED;
    this.metadata.invoiceNumber = invoiceNumber;
    this.markUpdated();

    this.addEvent(new InvoiceGeneratedEvent(
      this.id,
      invoiceNumber,
      this.customerId,
      this.totalAmount,
      this.currency,
      this.dueDate,
      this.updatedAt
    ));
  }

  public processPayment(
    paymentAmount: number,
    paymentMethod: string,
    paymentReference: string,
    transactionId?: string
  ): void {
    if (this.status !== BillingStatus.INVOICED) {
      throw new Error('Can only process payment for invoiced billing records');
    }

    if (paymentAmount <= 0) {
      throw new Error('Payment amount must be positive');
    }

    if (paymentAmount > this.totalAmount) {
      throw new Error('Payment amount cannot exceed total amount');
    }

    this.paymentMethod = paymentMethod;
    this.paymentReference = paymentReference;
    this.paidDate = new Date();
    this.transactionId = transactionId;

    if (paymentAmount === this.totalAmount) {
      this.paymentStatus = PaymentStatus.PAID;
      this.status = BillingStatus.PAID;
    } else {
      this.paymentStatus = PaymentStatus.PARTIAL;
      this.status = BillingStatus.PARTIALLY_PAID;
    }

    this.markUpdated();

    this.addEvent(new PaymentProcessedEvent(
      this.id,
      paymentAmount,
      paymentMethod,
      paymentReference,
      this.paymentStatus,
      this.paidDate,
      transactionId
    ));
  }

  public cancel(reason?: string): void {
    if (this.status === BillingStatus.PAID || this.status === BillingStatus.PARTIALLY_PAID) {
      throw new Error('Cannot cancel paid billing records');
    }

    this.status = BillingStatus.CANCELLED;
    this.markUpdated();

    if (reason) {
      this.metadata.cancellationReason = reason;
    }

    this.addEvent(new BillingUpdatedEvent(
      this.id,
      this.status,
      this.totalAmount,
      this.updatedAt
    ));
  }

  public refund(refundAmount: number, reason?: string): void {
    if (this.paymentStatus !== PaymentStatus.PAID && this.paymentStatus !== PaymentStatus.PARTIAL) {
      throw new Error('Can only refund paid billing records');
    }

    if (refundAmount <= 0) {
      throw new Error('Refund amount must be positive');
    }

    if (refundAmount > this.totalAmount) {
      throw new Error('Refund amount cannot exceed total amount');
    }

    this.paymentStatus = PaymentStatus.REFUNDED;
    this.status = BillingStatus.REFUNDED;
    this.markUpdated();

    if (reason) {
      this.metadata.refundReason = reason;
    }

    this.metadata.refundAmount = refundAmount;
    this.metadata.refundDate = new Date();
  }

  private calculateAmounts(): void {
    this.subtotal = this.items.reduce((sum, item) => sum + item.totalPrice, 0);
    this.taxAmount = this.items.reduce((sum, item) => sum + item.taxAmount, 0);
    this.totalAmount = this.subtotal + this.taxAmount - (this.discountAmount || 0);
  }

  private markUpdated(): void {
    this.updatedAt = new Date();
    this.version += 1;
  }

  private addEvent(event: any): void {
    this.uncommittedEvents.push(event);
  }

  public getUncommittedEvents(): any[] {
    return [...this.uncommittedEvents];
  }

  public markEventsAsCommitted(): void {
    this.uncommittedEvents = [];
  }

  public toSnapshot(): any {
    return {
      id: this.id,
      customerId: this.customerId,
      orderId: this.orderId,
      transactionId: this.transactionId,
      billingType: this.billingType,
      status: this.status,
      items: this.items,
      subtotal: this.subtotal,
      taxAmount: this.taxAmount,
      discountAmount: this.discountAmount,
      totalAmount: this.totalAmount,
      currency: this.currency,
      billingAddress: this.billingAddress,
      dueDate: this.dueDate,
      paidDate: this.paidDate,
      paymentStatus: this.paymentStatus,
      paymentMethod: this.paymentMethod,
      paymentReference: this.paymentReference,
      notes: this.notes,
      metadata: this.metadata,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      version: this.version,
    };
  }

  // Business rule validations
  public isOverdue(): boolean {
    if (!this.dueDate || this.status === BillingStatus.PAID) {
      return false;
    }
    return new Date() > this.dueDate;
  }

  public canBeModified(): boolean {
    return this.status === BillingStatus.DRAFT;
  }

  public canBeFinalized(): boolean {
    return this.status === BillingStatus.DRAFT && this.items.length > 0;
  }

  public canGenerateInvoice(): boolean {
    return this.status === BillingStatus.FINALIZED;
  }

  public canProcessPayment(): boolean {
    return this.status === BillingStatus.INVOICED;
  }

  public canBeCancelled(): boolean {
    return this.status !== BillingStatus.PAID && 
           this.status !== BillingStatus.PARTIALLY_PAID &&
           this.status !== BillingStatus.CANCELLED;
  }

  public canBeRefunded(): boolean {
    return this.paymentStatus === PaymentStatus.PAID || 
           this.paymentStatus === PaymentStatus.PARTIAL;
  }
}
