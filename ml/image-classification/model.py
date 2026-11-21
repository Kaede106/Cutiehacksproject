
import torch
import torch.nn as nn



class HealthClassifier(nn.Module):

    def __init__(self):

        super().__init__()

        self.network = nn.Sequential(

            nn.Linear(11010294, 128),

            nn.ReLU(),

            nn.Linear(128, 7)

        )


    def forward(self, x):

        return self.network(x)
