import joblib
import pandas as pd

my_dictionary = {
    "Low": 50,
    "Medium": 100,
    "High": 150
}

def predict(moisture, temperature, humidity):
    # sys.executable ensures it uses the exact same Python environment
    loaded_model = joblib.load("logistic_model.joblib")
    new_df = pd.DataFrame([{
    "Temperature_C": temperature,
    "Humidity": humidity,
    "Soil_Moisture": moisture
    }])
    result = loaded_model.predict(new_df)[0]
    return my_dictionary[result]
