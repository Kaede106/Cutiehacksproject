import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report

df = pd.read_csv(r"C:\Users\ralma\Documents\Cutiehacksproject\ml\data\irrigation_prediction.csv")

sub_df = df[df["Crop_Type"] == "Cotton"]

feature_df = sub_df[["Temperature_C", "Humidity", "Soil_Moisture"]]
target = sub_df["Irrigation_Need"]

X_train, X_test, y_train, y_test = train_test_split(
    feature_df, target, test_size=0.2, random_state=42
)

model = LogisticRegression()
model.fit(X_train, y_train)

