// templates/widget.js - The main widget JavaScript file

(function() {
    'use strict';
    
    // Get script tag and configuration
    var currentScript = document.currentScript;
    var domain = currentScript.getAttribute('data-domain');
    var position = currentScript.getAttribute('data-position') || 'bottom-right';
    var primaryColor = currentScript.getAttribute('data-color') || '#007bff';
    var apiBase = currentScript.src.replace('/widget.js', '');
    
    if (!domain) {
        console.error('Chatbot Widget: data-domain attribute is required');
        return;
    }
    
    // Widget state
    var isOpen = false;
    var sessionId = null;
    var messages = [];
    
    // Create widget HTML
    function createWidget() {
        var widgetHTML = `
            <div id="chatbot-widget" style="
                position: fixed;
                ${getPositionStyles(position)}
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            ">
                <!-- Chat Button -->
                <div id="chat-button" style="
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: ${primaryColor};
                    color: white;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                    font-size: 24px;
                    transition: all 0.3s ease;
                ">
                    💬
                </div>
                
                <!-- Chat Window -->
                <div id="chat-window" style="
                    width: 350px;
                    height: 500px;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 5px 40px rgba(0,0,0,0.15);
                    display: none;
                    flex-direction: column;
                    ${getWindowPosition(position)}
                ">
                    <!-- Header -->
                    <div style="
                        padding: 20px;
                        background: ${primaryColor};
                        color: white;
                        border-radius: 10px 10px 0 0;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    ">
                        <div>
                            <h3 style="margin: 0; font-size: 16px;">Chat Support</h3>
                            <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 12px;">We're here to help!</p>
                        </div>
                        <button id="close-chat" style="
                            background: none;
                            border: none;
                            color: white;
                            font-size: 20px;
                            cursor: pointer;
                            padding: 0;
                            width: 30px;
                            height: 30px;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        ">×</button>
                    </div>
                    
                    <!-- Messages -->
                    <div id="chat-messages" style="
                        flex: 1;
                        overflow-y: auto;
                        padding: 20px;
                        display: flex;
                        flex-direction: column;
                        gap: 15px;
                    "></div>
                    
                    <!-- Input -->
                    <div style="
                        padding: 20px;
                        border-top: 1px solid #eee;
                        display: flex;
                        gap: 10px;
                    ">
                        <input type="text" id="chat-input" placeholder="Type your message..." style="
                            flex: 1;
                            border: 1px solid #ddd;
                            border-radius: 20px;
                            padding: 10px 15px;
                            font-size: 14px;
                            outline: none;
                        ">
                        <button id="send-button" style="
                            background: ${primaryColor};
                            color: white;
                            border: none;
                            border-radius: 50%;
                            width: 40px;
                            height: 40px;
                            cursor: pointer;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        ">➤</button>
                        <button id="mic-button" style="
                            background: ${primaryColor};
                            color: white;
                            border: none;
                            border-radius: 50%;
                            width: 40px;
                            height: 40px;
                            cursor: pointer;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            margin-left: 5px;
                        ">🎙️</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', widgetHTML);
        setupEventListeners();
        loadInitialGreeting();
    }
    
    function getPositionStyles(position) {
        switch(position) {
            case 'bottom-left': return 'bottom: 20px; left: 20px;';
            case 'bottom-right': return 'bottom: 20px; right: 20px;';
            case 'top-left': return 'top: 20px; left: 20px;';
            case 'top-right': return 'top: 20px; right: 20px;';
            default: return 'bottom: 20px; right: 20px;';
        }
    }
    
    function getWindowPosition(position) {
        if (position.includes('bottom')) {
            return 'bottom: 80px;';
        } else {
            return 'top: 80px;';
        }
    }
    
    function setupEventListeners() {
        var chatButton = document.getElementById('chat-button');
        var closeButton = document.getElementById('close-chat');
        var sendButton = document.getElementById('send-button');
        var chatInput = document.getElementById('chat-input');
        var micButton = document.getElementById('mic-button');
        
        chatButton.addEventListener('click', toggleChat);
        closeButton.addEventListener('click', closeChat);
        sendButton.addEventListener('click', sendMessage);
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
        micButton.addEventListener('click', startVoiceInput);
    }
    
    function toggleChat() {
        var chatWindow = document.getElementById('chat-window');
        var chatButton = document.getElementById('chat-button');
        
        isOpen = !isOpen;
        
        if (isOpen) {
            chatWindow.style.display = 'flex';
            chatButton.innerHTML = '×';
        } else {
            chatWindow.style.display = 'none';
            chatButton.innerHTML = '💬';
        }
    }
    
    function closeChat() {
        isOpen = false;
        document.getElementById('chat-window').style.display = 'none';
        document.getElementById('chat-button').innerHTML = '💬';
    }
    
    function addMessage(content, isUser = false, showFAQs = false) {
        var messagesContainer = document.getElementById('chat-messages');
        
        var messageDiv = document.createElement('div');
        messageDiv.style.cssText = `
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            margin: ${isUser ? '0 0 0 auto' : '0 auto 0 0'};
            background: ${isUser ? primaryColor : '#f1f1f1'};
            color: ${isUser ? 'white' : '#333'};
            font-size: 14px;
            line-height: 1.4;
            word-wrap: break-word;
        `;
        
        messageDiv.innerHTML = content;
        messagesContainer.appendChild(messageDiv);
        
        // Add FAQ buttons if needed
        if (showFAQs && content.faqs && content.faqs.length > 0) {
            var faqContainer = document.createElement('div');
            faqContainer.style.cssText = 'margin-top: 10px; display: flex; flex-direction: column; gap: 5px;';
            
            content.faqs.forEach(function(faq) {
                var button = document.createElement('button');
                button.textContent = faq;
                button.style.cssText = `
                    background: white;
                    border: 1px solid ${primaryColor};
                    color: ${primaryColor};
                    padding: 8px 12px;
                    border-radius: 15px;
                    cursor: pointer;
                    font-size: 12px;
                    text-align: left;
                    transition: all 0.2s;
                `;
                
                button.addEventListener('click', function() {
                    sendMessage(faq);
                });
                
                button.addEventListener('mouseover', function() {
                    button.style.background = primaryColor;
                    button.style.color = 'white';
                });
                
                button.addEventListener('mouseout', function() {
                    button.style.background = 'white';
                    button.style.color = primaryColor;
                });
                
                faqContainer.appendChild(button);
            });
            
            messagesContainer.appendChild(faqContainer);
        }
        
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    function loadInitialGreeting() {
        fetch(apiBase + '/api/widget/greet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ domain: domain })
        })
        .then(response => response.json())
        .then(data => {
            if (data.greeting) {
                sessionId = data.session_id;
                addMessage(data.greeting);
                
                if (data.faqs && data.faqs.length > 0) {
                    addMessage({ faqs: data.faqs }, false, true);
                }
            }
        })
        .catch(error => {
            console.error('Widget greeting error:', error);
            addMessage('Hello! How can I help you today?');
        });
    }
    
    function sendMessage(messageText) {
        var input = document.getElementById('chat-input');
        var message = messageText || input.value.trim();
        
        if (!message) return;
        
        // Clear input
        if (!messageText) input.value = '';
        
        // Add user message
        addMessage(message, true);
        
        // Show typing indicator
        var typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.style.cssText = `
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            background: #f1f1f1;
            color: #666;
            font-size: 14px;
            font-style: italic;
        `;
        typingDiv.innerHTML = 'Typing...';
        document.getElementById('chat-messages').appendChild(typingDiv);
        
        // Send to API
        fetch(apiBase + '/api/widget/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                domain: domain,
                message: message,
                session_id: sessionId
            })
        })
        .then(response => response.json())
        .then(data => {
            // Remove typing indicator
            var typing = document.getElementById('typing-indicator');
            if (typing) typing.remove();
            
            if (data.response) {
                addMessage(data.response);
                sessionId = data.session_id;
            } else {
                addMessage('Sorry, I encountered an error. Please try again.');
            }
        })
        .catch(error => {
            // Remove typing indicator
            var typing = document.getElementById('typing-indicator');
            if (typing) typing.remove();
            
            console.error('Widget chat error:', error);
            addMessage('Sorry, I encountered an error. Please try again.');
        });
    }
    
    function startVoiceInput() {
        if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
            alert('Voice input not supported in this browser.');
            return;
        }
        var recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onresult = function(event) {
            var transcript = event.results[0][0].transcript;
            document.getElementById('chat-input').value = transcript;
        };
        recognition.onerror = function(event) {
            alert('Voice input error: ' + event.error);
        };
        recognition.start();
    }
    
    // Initialize widget when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createWidget);
    } else {
        createWidget();
    }
})();