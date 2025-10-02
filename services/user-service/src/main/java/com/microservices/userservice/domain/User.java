package com.microservices.userservice.domain;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "users")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String firstName;

    @Column(nullable = false)
    private String lastName;

    @Column(nullable = false)
    private String phoneNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserStatus status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal creditLimit;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal availableCredit;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal usedCredit;

    @CreationTimestamp
    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(nullable = false)
    private LocalDateTime updatedAt;

    @Version
    private Long version;

    public enum UserStatus {
        ACTIVE,
        INACTIVE,
        SUSPENDED,
        DELETED
    }

    public boolean canReserveCredit(BigDecimal amount) {
        return status == UserStatus.ACTIVE && 
               availableCredit.compareTo(amount) >= 0;
    }

    public void reserveCredit(BigDecimal amount) {
        if (!canReserveCredit(amount)) {
            throw new IllegalStateException("Insufficient credit available");
        }
        this.availableCredit = this.availableCredit.subtract(amount);
        this.usedCredit = this.usedCredit.add(amount);
    }

    public void releaseCredit(BigDecimal amount) {
        this.availableCredit = this.availableCredit.add(amount);
        this.usedCredit = this.usedCredit.subtract(amount);
        
        // Ensure we don't go below zero
        if (this.usedCredit.compareTo(BigDecimal.ZERO) < 0) {
            this.usedCredit = BigDecimal.ZERO;
        }
    }

    public void confirmCreditUsage(BigDecimal amount) {
        // Credit is already reserved, just ensure consistency
        if (this.usedCredit.compareTo(amount) < 0) {
            throw new IllegalStateException("Cannot confirm more credit than reserved");
        }
    }

    public void updateCreditLimit(BigDecimal newLimit) {
        BigDecimal difference = newLimit.subtract(this.creditLimit);
        this.creditLimit = newLimit;
        this.availableCredit = this.availableCredit.add(difference);
    }
}
