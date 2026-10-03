FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /b
COPY pom.xml .
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q package -DskipTests

FROM eclipse-temurin:17-jre
COPY --from=build /b/target/fleet-backend-1.0.0.jar /app.jar
ENTRYPOINT ["java","-jar","/app.jar"]
