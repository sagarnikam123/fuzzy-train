# Multi-stage build for fuzzy-train-skywalking Java

# Stage 1: Build
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build
COPY pom.xml .
COPY src ./src

RUN mvn clean package -DskipTests

# Stage 2: Runtime with SkyWalking Agent
FROM eclipse-temurin:21-jre

LABEL maintainer="sagarnikam123"
LABEL description="Fake log generator with SkyWalking integration (Java)"

WORKDIR /app

# Download and extract SkyWalking Java Agent
ARG SW_AGENT_VERSION=9.3.0
RUN apt-get update && apt-get install -y wget && \
    wget -qO- https://archive.apache.org/dist/skywalking/java-agent/${SW_AGENT_VERSION}/apache-skywalking-java-agent-${SW_AGENT_VERSION}.tgz \
    | tar xz -C /opt && \
    mv /opt/skywalking-agent /opt/skywalking && \
    apt-get remove -y wget && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy the built JAR
COPY --from=builder /build/target/fuzzy-train-skywalking-1.0.0.jar /app/fuzzy-train-skywalking.jar

# Default environment variables
ENV SW_AGENT_NAME="skywalking-test::fuzzy-train-java"
ENV SW_AGENT_COLLECTOR_BACKEND_SERVICES="skywalking-satellite.skywalking.svc:11800"
ENV SW_GRPC_LOG_SERVER_HOST="skywalking-satellite.skywalking.svc"
ENV SW_GRPC_LOG_SERVER_PORT="11800"
ENV SW_LOGGING_LEVEL="INFO"
ENV SW_LOGGING_OUTPUT="CONSOLE"

# Java 21 ByteBuddy fix
ENV JDK_JAVA_OPTIONS="-Dorg.apache.skywalking.apm.dependencies.net.bytebuddy.experimental=true"

# Run with SkyWalking agent
ENTRYPOINT ["java", "-javaagent:/opt/skywalking/skywalking-agent.jar", "-jar", "/app/fuzzy-train-skywalking.jar"]
CMD ["--lines-per-second", "1"]
