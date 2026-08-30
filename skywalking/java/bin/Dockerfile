# Multi-stage build for fuzzy-train-skywalking Java

# Stage 1: Build
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
COPY src ./src

RUN mvn clean package -DskipTests

# Stage 2: Runtime — no bundled SkyWalking agent
# Agent is injected by SWCK operator via init container at /sky/agent/
FROM eclipse-temurin:21-jre

LABEL maintainer="sagarnikam123"
LABEL description="Fake log generator with SkyWalking integration (Java)"

WORKDIR /app

# Copy the built JAR
COPY --from=builder /build/target/fuzzy-train-skywalking-1.0.0.jar /app/fuzzy-train-skywalking.jar

# Default environment variables
ENV SW_AGENT_NAME="skywalking-test::fuzzy-train-java"
ENV SW_AGENT_COLLECTOR_BACKEND_SERVICES="skywalking-satellite.skywalking.svc:11800"
ENV SW_GRPC_LOG_SERVER_HOST="skywalking-satellite.skywalking.svc"
ENV SW_GRPC_LOG_SERVER_PORT="11800"
ENV SW_LOGGING_LEVEL="INFO"
ENV SW_LOGGING_OUTPUT="CONSOLE"

# Java 21 ByteBuddy fix for SkyWalking agent
ENV JDK_JAVA_OPTIONS="-Dorg.apache.skywalking.apm.dependencies.net.bytebuddy.experimental=true"

# Run without explicit -javaagent — SWCK injects it via JAVA_TOOL_OPTIONS
ENTRYPOINT ["java", "-jar", "/app/fuzzy-train-skywalking.jar"]
CMD ["--lines-per-second", "1"]
