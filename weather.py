from flask import Flask, request, jsonify, render_template_string
from autogen import UserProxyAgent, AssistantAgent
import autogen
import requests
import logging

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Load AutoGen configuration
config_list_gemini = autogen.config_list_from_json("model_config.json")


def extract_city(text, geniagent):
    """Extracts city name from query using a GenAI agent."""
    prompt = f"Extract the city name from this sentence: '{text}'. If no city is found, return 'None'."
    response = geniagent.generate_reply([{"role": "user", "content": prompt}])
    city = response[0].get("content", "None").strip() if isinstance(response, list) else response.get("content", "None").strip()
    print(city)
    return city if city.lower() != "none" else None

def get_weather(city):
    """Fetch current weather information using Open-Meteo API."""
    if not city:
        return None
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&format=json"
    geo_response = requests.get(geo_url).json()
    if not geo_response.get("results"):
        return None
    location = geo_response["results"][0]
    lat, lon = location["latitude"], location["longitude"]
    
    # Updated to include cloud_cover in the API request
    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,cloud_cover&timezone=auto"
    weather_response = requests.get(weather_url).json()
    current_weather = weather_response.get("current", {})
    
    temperature = current_weather.get("temperature_2m", "N/A")
    humidity = current_weather.get("relative_humidity_2m", "N/A")
    wind_speed = current_weather.get("wind_speed_10m", "N/A")
    cloud_cover = current_weather.get("cloud_cover", "N/A")
    
    # Determine sky condition based on cloud cover percentage
    if cloud_cover != "N/A":
        if cloud_cover < 20:
            sky_condition = "clear skies"
        elif 20 <= cloud_cover < 70:
            sky_condition = "partly cloudy"
        else:
            sky_condition = "cloudy"
    else:
        sky_condition = "unknown cloud conditions"
    
    return (
        f"The current weather in {city} is {temperature}°C with {humidity}% humidity, "
        f"wind speed of {wind_speed} km/h, and {sky_condition} ({cloud_cover}% cloud cover)."
    )



# Create the assistant agent
assistant = AssistantAgent(
    name="Weather Assistant",
    system_message=(
        "Act as a real-time weather information provider. If asked about the weather, "
        "extract the city name from the user's query and provide the relevant weather forecast."
    ),
    llm_config={"config_list": config_list_gemini},
    code_execution_config=False
)

user_proxy = UserProxyAgent(
    name="User",
    system_message="Ask about the weather or anything else, and I will fetch the information for you.",
    human_input_mode="ALWAYS",
    code_execution_config={"use_docker": False}
)

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chatbot</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body { background: #f8f9fa; font-family: Arial, sans-serif; text-align: center; }
            .chat-container { max-width: 500px; margin: 50px auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1); }
            .chat-log { height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; background: #fff; }
            .user { color: blue; font-weight: bold; }
            .bot { color: green; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <h2>Chatbot</h2>
            <div class="chat-log" id="chatLog"></div>
            <input type="text" id="userInput" class="form-control" placeholder="Ask something..." onkeypress="handleKeyPress(event)">
            <button class="btn btn-primary mt-2" onclick="sendMessage()">Send</button>
            <button class="btn btn-danger mt-2" onclick="clearChat()">Clear</button>
        </div>
        <script>
            function sendMessage() {
                let inputField = document.getElementById("userInput");
                let message = inputField.value.trim();
                if (message === "") return;
                let chatLog = document.getElementById("chatLog");
                chatLog.innerHTML += "<p class='user'>You: " + message + "</p>";
                fetch("/query?text=" + encodeURIComponent(message))
                .then(response => response.json())
                .then(data => {
                    chatLog.innerHTML += "<p class='bot'>Bot: " + data.response + "</p>";
                    chatLog.scrollTop = chatLog.scrollHeight;
                });
                inputField.value = "";
            }
            function handleKeyPress(event) {
                if (event.key === "Enter") {
                    sendMessage();
                }
            }
            function clearChat() {
                document.getElementById("chatLog").innerHTML = "";
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/query')
def query():
    text = request.args.get('text', '').strip()
    if not text:
        return jsonify({"response": "Please enter a question."})

    logging.debug(f"Received query: {text}")

    # Extract city from the query
    city = extract_city(text, assistant)
    weather_info = None

    if city:
        weather_info = get_weather(city)

    # Construct final query for the AI
    final_query = text
    if weather_info:
        final_query += f" answer this if the weather in {city} is: {weather_info}"
    print(final_query)
    # Get AI response
    ai_response = assistant.generate_reply([{"role": "user", "content": final_query}])
    response = ai_response[0].get("content", "I didn't understand that.") if isinstance(ai_response, list) else ai_response.get("content", "I didn't understand that.")

    logging.debug(f"Response: {response}")
    return jsonify({"response": response})



if __name__ == "__main__":
    app.run(debug=True)