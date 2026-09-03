# Order Processing State Machine Definition

## Config

- **prefix**: Order

## Context Definition Table

| **context_name** | **field_type** | **field_name** | **description** |
| ----------------- | --------------- | --------------- | ----------------- |
| OrderContext      | std::string     | orderId         | Unique identifier for the order |
| OrderContext      | double          | totalAmount     | Total monetary amount of the order |
| OrderContext      | std::string     | customerId      | Unique identifier for the customer |

## State Definition Table

| **id** | **name** | **type** | **description** |
| ------ | -------- | -------- | ---------------- |
| S000   | Pending  | initial  | Order has been created and is awaiting payment |
| S001   | Paid     | normal   | Payment has been received and order is ready for delivery |
| S002   | Completed | final    | Order has been successfully delivered and processed |

## State Transition Table

| **id** | **from_state** | **event** | **guard** | **to_state** | **action** | **description** |
| ------ | -------------- | --------- | --------- | ------------ | ---------- | ---------------- |
| T001   | Pending        | PaymentReceived |           | Paid         | RecordPayment | Payment is received for the pending order |
| T002   | Paid           | OrderDelivered  |           | Completed    | MarkAsDelivered | Order is delivered to the customer and marked complete |