import joblib

my_dictionary = {
    "Low": 50,
    "Medium": 100,
    "High": 150
}

def predict(moisture, temperature, humidity):
    # sys.executable ensures it uses the exact same Python environment
    loaded_model = joblib.load("logistic_model.joblib")
    result = loaded_model.predict([[temperature, humidity, moisture]])[0]
    return my_dictionary[result]