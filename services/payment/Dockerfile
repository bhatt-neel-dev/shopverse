FROM golang:1.22-alpine AS build
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY main.go .
RUN CGO_ENABLED=0 go build -o payment .

FROM alpine:3.20
WORKDIR /app
COPY --from=build /build/payment .
EXPOSE 8085
CMD ["./payment"]
