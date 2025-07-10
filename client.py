import requests

print("🤖 Inara Support Bot (type 'exit' to quit)")

# Infinite loop to chat with bot via terminal
while True:
    msg = input("You: ")
    
    if msg.lower() == 'exit':
        break
    
    # Send user input to server and get response
    res = requests.post("http://localhost:5000/chat", json={"message": msg})
    
    # Display bot's reply
    print("Bot:", res.json()['response'])
