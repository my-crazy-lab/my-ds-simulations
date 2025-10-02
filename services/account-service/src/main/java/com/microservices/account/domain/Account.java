package com.microservices.account.domain;

import com.microservices.account.domain.events.*;
import lombok.NoArgsConstructor;
import org.axonframework.commandhandling.CommandHandler;
import org.axonframework.eventsourcing.EventSourcingHandler;
import org.axonframework.modelling.command.AggregateIdentifier;
import org.axonframework.modelling.command.AggregateLifecycle;
import org.axonframework.spring.stereotype.Aggregate;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import static org.axonframework.modelling.command.AggregateLifecycle.apply;

@Aggregate
@NoArgsConstructor
public class Account {

    @AggregateIdentifier
    private UUID accountId;
    private String accountNumber;
    private String customerId;
    private AccountType accountType;
    private AccountStatus status;
    private BigDecimal balance;
    private BigDecimal availableBalance;
    private BigDecimal reservedAmount;
    private String currency;
    private Instant createdAt;
    private Instant updatedAt;

    @CommandHandler
    public Account(CreateAccountCommand command) {
        apply(AccountCreatedEvent.builder()
                .accountId(command.getAccountId())
                .accountNumber(command.getAccountNumber())
                .customerId(command.getCustomerId())
                .accountType(command.getAccountType())
                .currency(command.getCurrency())
                .initialBalance(command.getInitialBalance())
                .createdAt(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(DepositMoneyCommand command) {
        if (status != AccountStatus.ACTIVE) {
            throw new IllegalStateException("Account is not active");
        }

        if (command.getAmount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("Deposit amount must be positive");
        }

        apply(MoneyDepositedEvent.builder()
                .accountId(command.getAccountId())
                .transactionId(command.getTransactionId())
                .amount(command.getAmount())
                .description(command.getDescription())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(WithdrawMoneyCommand command) {
        if (status != AccountStatus.ACTIVE) {
            throw new IllegalStateException("Account is not active");
        }

        if (command.getAmount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("Withdrawal amount must be positive");
        }

        if (availableBalance.compareTo(command.getAmount()) < 0) {
            throw new IllegalStateException("Insufficient funds");
        }

        apply(MoneyWithdrawnEvent.builder()
                .accountId(command.getAccountId())
                .transactionId(command.getTransactionId())
                .amount(command.getAmount())
                .description(command.getDescription())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(ReserveMoneyCommand command) {
        if (status != AccountStatus.ACTIVE) {
            throw new IllegalStateException("Account is not active");
        }

        if (command.getAmount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException("Reserve amount must be positive");
        }

        if (availableBalance.compareTo(command.getAmount()) < 0) {
            throw new IllegalStateException("Insufficient funds for reservation");
        }

        apply(MoneyReservedEvent.builder()
                .accountId(command.getAccountId())
                .reservationId(command.getReservationId())
                .transactionId(command.getTransactionId())
                .amount(command.getAmount())
                .description(command.getDescription())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(ReleaseReservationCommand command) {
        if (reservedAmount.compareTo(command.getAmount()) < 0) {
            throw new IllegalStateException("Cannot release more than reserved amount");
        }

        apply(ReservationReleasedEvent.builder()
                .accountId(command.getAccountId())
                .reservationId(command.getReservationId())
                .transactionId(command.getTransactionId())
                .amount(command.getAmount())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(ConfirmReservationCommand command) {
        if (reservedAmount.compareTo(command.getAmount()) < 0) {
            throw new IllegalStateException("Cannot confirm more than reserved amount");
        }

        apply(ReservationConfirmedEvent.builder()
                .accountId(command.getAccountId())
                .reservationId(command.getReservationId())
                .transactionId(command.getTransactionId())
                .amount(command.getAmount())
                .description(command.getDescription())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(FreezeAccountCommand command) {
        if (status == AccountStatus.FROZEN) {
            return; // Already frozen
        }

        apply(AccountFrozenEvent.builder()
                .accountId(command.getAccountId())
                .reason(command.getReason())
                .timestamp(Instant.now())
                .build());
    }

    @CommandHandler
    public void handle(UnfreezeAccountCommand command) {
        if (status != AccountStatus.FROZEN) {
            throw new IllegalStateException("Account is not frozen");
        }

        apply(AccountUnfrozenEvent.builder()
                .accountId(command.getAccountId())
                .timestamp(Instant.now())
                .build());
    }

    // Event Sourcing Handlers
    @EventSourcingHandler
    public void on(AccountCreatedEvent event) {
        this.accountId = event.getAccountId();
        this.accountNumber = event.getAccountNumber();
        this.customerId = event.getCustomerId();
        this.accountType = event.getAccountType();
        this.status = AccountStatus.ACTIVE;
        this.balance = event.getInitialBalance();
        this.availableBalance = event.getInitialBalance();
        this.reservedAmount = BigDecimal.ZERO;
        this.currency = event.getCurrency();
        this.createdAt = event.getCreatedAt();
        this.updatedAt = event.getCreatedAt();
    }

    @EventSourcingHandler
    public void on(MoneyDepositedEvent event) {
        this.balance = this.balance.add(event.getAmount());
        this.availableBalance = this.availableBalance.add(event.getAmount());
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(MoneyWithdrawnEvent event) {
        this.balance = this.balance.subtract(event.getAmount());
        this.availableBalance = this.availableBalance.subtract(event.getAmount());
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(MoneyReservedEvent event) {
        this.availableBalance = this.availableBalance.subtract(event.getAmount());
        this.reservedAmount = this.reservedAmount.add(event.getAmount());
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(ReservationReleasedEvent event) {
        this.availableBalance = this.availableBalance.add(event.getAmount());
        this.reservedAmount = this.reservedAmount.subtract(event.getAmount());
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(ReservationConfirmedEvent event) {
        this.balance = this.balance.subtract(event.getAmount());
        this.reservedAmount = this.reservedAmount.subtract(event.getAmount());
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(AccountFrozenEvent event) {
        this.status = AccountStatus.FROZEN;
        this.updatedAt = event.getTimestamp();
    }

    @EventSourcingHandler
    public void on(AccountUnfrozenEvent event) {
        this.status = AccountStatus.ACTIVE;
        this.updatedAt = event.getTimestamp();
    }

    // Getters
    public UUID getAccountId() { return accountId; }
    public String getAccountNumber() { return accountNumber; }
    public String getCustomerId() { return customerId; }
    public AccountType getAccountType() { return accountType; }
    public AccountStatus getStatus() { return status; }
    public BigDecimal getBalance() { return balance; }
    public BigDecimal getAvailableBalance() { return availableBalance; }
    public BigDecimal getReservedAmount() { return reservedAmount; }
    public String getCurrency() { return currency; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
