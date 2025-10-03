# Build stage
FROM golang:1.21-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev

# Install RocksDB dependencies
RUN apk add --no-cache \
    rocksdb-dev \
    rocksdb-static \
    snappy-dev \
    lz4-dev \
    zstd-dev \
    bzip2-dev

# Set working directory
WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Generate protobuf files
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
RUN go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
RUN apk add --no-cache protobuf-dev
RUN protoc --go_out=. --go-grpc_out=. proto/raft.proto

# Build the application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o raft-node .

# Runtime stage
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache \
    rocksdb \
    snappy \
    lz4-libs \
    zstd-libs \
    bzip2-libs \
    curl \
    ca-certificates

# Create app user
RUN addgroup -g 1001 -S raft && \
    adduser -u 1001 -S raft -G raft

# Create directories
RUN mkdir -p /data /wal /app && \
    chown -R raft:raft /data /wal /app

# Copy binary from builder stage
COPY --from=builder /app/raft-node /app/raft-node

# Set ownership
RUN chown raft:raft /app/raft-node

# Switch to app user
USER raft

# Set working directory
WORKDIR /app

# Expose ports
EXPOSE 8080 9090 7070

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["./raft-node"]
