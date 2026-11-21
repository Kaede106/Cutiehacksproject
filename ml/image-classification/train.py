
import torch
import torch.nn as nn

from dataset import CitrusDataset
from model import HealthClassifier

from torch.utils.data import DataLoader

from torch.utils.data import random_split


# Hyperparameters
BATCH_SIZE = 32
LEARNING_RATE = 0.01
NUM_EPOCHS = 10


# Load training dataset
train_dataset = CitrusDataset("C:/Users/ralma/Documents/face-to-emoji/data/train")

train_size = int(0.8 * len(train_dataset))
val_size = len(train_dataset) - train_size

train_dataset, val_dataset = random_split(
    train_dataset,
    [train_size, val_size]
)

print("Training samples:", len(train_dataset))
print("Validation samples:", len(val_dataset))

train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True
)

val_loader = DataLoader(
    val_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False
)

# Initialize model, loss function, and optimizer
model = HealthClassifier()

criterion = nn.CrossEntropyLoss()

optimizer = torch.optim.SGD(
    model.parameters(),
    lr=LEARNING_RATE
)


# Training loop
for epoch in range(NUM_EPOCHS):

    model.train()

    total_loss = 0.0

    for images, labels in train_loader:

        # Clear previous gradients
        optimizer.zero_grad()

        # Forward pass
        logits = model(images)

        # Calculate loss
        loss = criterion(logits, labels)

        # Backpropagation
        loss.backward()

        # Update parameters
        optimizer.step()

        total_loss += loss.item()

    average_loss = total_loss / len(train_loader)

    print(
        f"Epoch [{epoch + 1}/{NUM_EPOCHS}], "
        f"Loss: {average_loss:.4f}"
    )

        # Validation
    model.eval()

    val_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():

        for images, labels in val_loader:

            # Forward pass
            logits = model(images)

            # Calculate loss
            loss = criterion(logits, labels)

            val_loss += loss.item() * images.size(0)

            # Get predictions
            predictions = logits.argmax(dim=1)

            # Count correct predictions
            correct += (predictions == labels).sum().item()
            total += labels.size(0)

    average_val_loss = val_loss / total
    accuracy = correct / total

    print(
        f"Validation Loss: {average_val_loss:.4f}, "
        f"Accuracy: {accuracy:.2%}"
    )

torch.save(model.state_dict(), "emotion_model.pth")