
from pathlib import Path

import torch
from torch.utils.data import Dataset
from torchvision.io import read_image



CONDITION = [
    "healthy",
    "citrus_canker",
    "melanose"
]


class CitrusDataset(Dataset):

    def __init__(self, root_dir):

        self.root_dir = Path(root_dir)

        self.samples = []

        for label, condition in enumerate(CONDITION):

            condition_dir = self.root_dir / condition

            for image_path in condition_dir.iterdir():

                self.samples.append((image_path, label))


    def __len__(self):

        return len(self.samples)


    def __getitem__(self, index):

        image_path, label = self.samples[index]

        image = read_image(str(image_path))

        # Convert pixel values to floating point in [0, 1]
        image = image.float() / 255.0

        # Flatten the image
        image = image.flatten()

        label = torch.tensor(label, dtype=torch.long)

        return image, label
