from ultralytics import YOLO
from PIL import Image

# Load a pretrained model
model = YOLO("yolo26n.pt")

# Run object detection
#results = model.predict(
    #source="orange.jpg",
    #save=True
#)


import torch
import torch.nn as nn
import torch.optim as optim

import torchvision
import torchvision.transforms as transforms

transform = transforms.Compose([
    transforms.Resize((128, 128)),
    transforms.ToTensor(),
    transforms.Normalize(
        (0.5, 0.5, 0.5),
        (0.5, 0.5, 0.5)
    )
])

class OrangeCNN(nn.Module):

    def __init__(self):
        super().__init__()

        self.conv1 = nn.Conv2d(
            in_channels=3,
            out_channels=32,
            kernel_size=3,
            stride=1,
            padding=1
        )

        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)


        self.relu = nn.ReLU()

        self.pool = nn.MaxPool2d(
            kernel_size=2,
            stride=2
        )

        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))
        self.flatten = nn.Flatten()

        self.fc1 = nn.Linear(64 * 4 * 4, 128)
        self.fc2 = nn.Linear(128, 3)

    def forward(self, x):

        x = self.conv1(x)
        x = self.relu(x)
        x = self.pool(x)

        x = self.conv2(x)
        x = self.relu(x)
        x = self.pool(x)

        x = self.adaptive_pool(x)
        x = self.flatten(x)

        x = self.fc1(x)
        x = self.relu(x)

        x = self.fc2(x)


        return x

    
orange_model = OrangeCNN()

orange_model.load_state_dict(
    torch.load("orange_cnn.pth", map_location="cpu", weights_only=True)
)

orange_model.eval()

def init_pred(source):
    results = model.predict(
        source=source,       # Default webcam
        stream=True,    # Process frames continuously
        show=True,
        conf=0.5,
        classes=[49]
    )

    output_thing = []
    for result in results:
        for box in result.boxes:
            # Get bounding box coordinates
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            print("Top-left:", (x1, y1))
            print("Bottom-right:", (x2, y2))
            # Crop the image to the bounding box
            raw_cropped = result.orig_img[int(y1):int(y2), int(x1):int(x2)]
            temp_cropped_image = Image.fromarray(raw_cropped)
            cropped_image = transform(temp_cropped_image).unsqueeze(0)  # Add batch dimension
            with torch.no_grad():
                outputs = orange_model(cropped_image)
                predictions = outputs.argmax(dim=1)
            if predictions.item() != 0:
                print("The orange is diseased.")
            else:
                print("The orange is healthy.")
                output_thing.append(((x1+x2)/2, (y1+y2)/2))  # Append the center coordinates of the bounding box



    return output_thing


    
