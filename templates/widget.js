// templates/widget.js - Premium Professional Widget

(function () {
    'use strict';

    var currentScript = document.currentScript;
    var domain = currentScript.getAttribute('data-domain');
    var position = currentScript.getAttribute('data-position') || 'bottom-right';
    var primaryColor = currentScript.getAttribute('data-color') || '#007bff';
    var apiBase = currentScript.src.replace('/widget.js', '');

    if (!domain) {
        console.error('Chatbot Widget: data-domain attribute is required');
        return;
    }

    var isOpen = false;
    var sessionId = null;
    var messages = [];

    // Create premium widget HTML
    function createWidget() {
        // Add CSS animations
        var style = document.createElement('style');
        style.textContent = `
            @keyframes slideUp {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes dotPulse {
                0%, 80%, 100% { opacity: 0.3; }
                40% { opacity: 1; }
            }
            #chat-messages::-webkit-scrollbar {
                width: 6px;
            }
            #chat-messages::-webkit-scrollbar-track {
                background: transparent;
            }
            #chat-messages::-webkit-scrollbar-thumb {
                background: #cbd5e0;
                border-radius: 3px;
            }
            #chat-messages::-webkit-scrollbar-thumb:hover {
                background: #a0aec0;
            }
        `;
        document.head.appendChild(style);

        var widgetHTML = `
            <div id="chatbot-widget" style="
                position: fixed;
                ${getPositionStyles(position)}
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            ">
                <!-- Chat Button - Opens chat only -->
                <div id="chat-button" style="
                    width: 64px;
                    height: 64px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, ${primaryColor} 0%, ${darkenColor(primaryColor, 15)} 100%);
                    color: white;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.15), 0 4px 8px rgba(0,0,0,0.1);
                    font-size: 30px;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                    padding: 10px;
                ">
                    <img src="${apiBase}/static/logo.png" alt="Chat" style="width: 70px; height: auto; border-radius: 8px;">
                </div>
                
                <!-- Chat Window -->
                <div id="chat-window" style="
                    width: 380px;
                    height: 600px;
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.15), 0 8px 24px rgba(0,0,0,0.1);
                    display: none;
                    flex-direction: column;
                    overflow: hidden;
                    ${getWindowPosition(position)}
                    animation: slideUp 0.3s ease;
                ">
                    <!-- Header -->
                    <div style="
                        padding: 28px 24px;
                        background: linear-gradient(135deg, ${primaryColor} 0%, ${darkenColor(primaryColor, 12)} 100%);
                        color: white;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    ">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <img src="${apiBase}/static/logo.png" alt="Aura AI" style="width: 100px; height: auto; border-radius: 8px;">
                            <div>
                                <h3 style="margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.3px;">Chat Support</h3>
                                <p style="margin: 8px 0 0 0; opacity: 0.93; font-size: 14px; font-weight: 400; color: #ffffff;">
  Online • Ready to help
</p>
</div>
                        </div>
                        <button id="close-chat" style="
                            background: rgba(255,255,255,0.2);
                            border: none;
                            color: white;
                            font-size: 26px;
                            cursor: pointer;
                            padding: 0;
                            width: 40px;
                            height: 40px;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            transition: all 0.2s;
                            backdrop-filter: blur(10px);
                            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                            font-weight: 300;
                            line-height: 1;
                        ">×</button>
                    </div>
                    
                    <!-- Messages with Geometric Shapes -->
                    <div id="chat-messages" style="
                        flex: 1;
                        overflow-y: auto;
                        padding: 24px;
                        background: #f8f9fa;
                        display: flex;
                        flex-direction: column;
                        gap: 16px;
                        position: relative;
                    ">
                        <!-- Geometric Shapes -->
                        <div style="position: absolute; width: 120px; height: 120px; background: linear-gradient(135deg, #a8b5ff 0%, #c5b3ff 100%); top: -40px; right: -30px; border-radius: 40% 60% 70% 30% / 40% 50% 60% 50%; opacity: 0.3; pointer-events: none; z-index: 0;"></div>
                        <div style="position: absolute; width: 100px; height: 100px; background: linear-gradient(135deg, #ffb3ba 0%, #ffcccb 100%); bottom: 20px; left: -30px; border-radius: 60% 40% 30% 70% / 60% 30% 70% 40%; opacity: 0.3; pointer-events: none; z-index: 0;"></div>
                        <div style="position: absolute; width: 80px; height: 80px; background: linear-gradient(135deg, #bae1ff 0%, #a2d5f2 100%); top: 50%; right: -20px; border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%; opacity: 0.3; pointer-events: none; z-index: 0;"></div>
                    </div>
                    
                    <!-- Input Area -->
                    <div style="
                        padding: 20px 24px;
                        background: white;
                        border-top: 1px solid #e9ecef;
                        display: flex;
                        gap: 10px;
                        align-items: center;
                        box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
                    ">
                        <input 
                            type="text" 
                            id="chat-input" 
                            placeholder="Type your message..." 
                            style="
                                flex: 1;
                                padding: 14px 18px;
                                border: 2px solid #e9ecef;
                                border-radius: 12px;
                                font-size: 15px;
                                outline: none;
                                transition: all 0.3s ease;
                                background: #f8f9fa;
                                font-family: inherit;
                            "
                        />
                        <button id="send-button" style="
                            padding: 14px 20px;
                            background: linear-gradient(135deg, ${primaryColor} 0%, ${darkenColor(primaryColor, 12)} 100%);
                            color: white;
                            border: none;
                            border-radius: 12px;
                            cursor: pointer;
                            font-weight: 600;
                            font-size: 15px;
                            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
                            min-width: 70px;
                            max-width: 80px;
                            flex-shrink: 0;
                        ">Send</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', widgetHTML);
        setupEventListeners();
        loadInitialGreeting();
        addHoverEffects();
    }

    function darkenColor(color, percent) {
        var num = parseInt(color.replace("#", ""), 16);
        var amt = Math.round(2.55 * percent);
        var R = (num >> 16) - amt;
        var G = (num >> 8 & 0x00FF) - amt;
        var B = (num & 0x0000FF) - amt;
        return "#" + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
            (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255))
            .toString(16).slice(1);
    }

    function addHoverEffects() {
        var chatButton = document.getElementById('chat-button');
        var closeButton = document.getElementById('close-chat');
        var sendButton = document.getElementById('send-button');
        var chatInput = document.getElementById('chat-input');

        chatButton.addEventListener('mouseover', function () {
            this.style.transform = 'scale(1.08) translateY(-2px)';
            this.style.boxShadow = '0 12px 32px rgba(0,0,0,0.2), 0 6px 12px rgba(0,0,0,0.15)';
        });
        chatButton.addEventListener('mouseout', function () {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 8px 24px rgba(0,0,0,0.15), 0 4px 8px rgba(0,0,0,0.1)';
        });

        closeButton.addEventListener('mouseover', function () {
            this.style.background = 'rgba(255,255,255,0.25)';
            this.style.transform = 'rotate(90deg)';
        });
        closeButton.addEventListener('mouseout', function () {
            this.style.background = 'rgba(255,255,255,0.15)';
            this.style.transform = 'rotate(0deg)';
        });

        sendButton.addEventListener('mouseover', function () {
            this.style.transform = 'scale(1.05)';
            this.style.boxShadow = '0 6px 16px rgba(0,0,0,0.2)';
        });
        sendButton.addEventListener('mouseout', function () {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        });

        chatInput.addEventListener('focus', function () {
            this.style.borderColor = primaryColor;
            this.style.background = 'white';
            this.style.boxShadow = '0 0 0 4px rgba(0,123,255,0.1)';
        });
        chatInput.addEventListener('blur', function () {
            this.style.borderColor = '#e2e8f0';
            this.style.background = '#f7fafc';
            this.style.boxShadow = 'none';
        });
    }

    function getPositionStyles(position) {
        switch (position) {
            case 'bottom-left': return 'bottom: 24px; left: 24px;';
            case 'bottom-right': return 'bottom: 24px; right: 24px;';
            case 'top-left': return 'top: 24px; left: 24px;';
            case 'top-right': return 'top: 24px; right: 24px;';
            default: return 'bottom: 24px; right: 24px;';
        }
    }

    function getWindowPosition(position) {
        if (position.includes('bottom')) {
            return 'bottom: 100px;';
        } else {
            return 'top: 100px;';
        }
    }

    function setupEventListeners() {
        var chatButton = document.getElementById('chat-button');
        var closeButton = document.getElementById('close-chat');
        var sendButton = document.getElementById('send-button');
        var chatInput = document.getElementById('chat-input');

        chatButton.addEventListener('click', toggleChat);
        closeButton.addEventListener('click', closeChat);
        sendButton.addEventListener('click', sendMessage);
        chatInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') sendMessage();
        });
    }

    function toggleChat() {
        var chatWindow = document.getElementById('chat-window');
        var chatButton = document.getElementById('chat-button');

        // Only open the chat, don't close it
        if (!isOpen) {
            isOpen = true;
            chatWindow.style.display = 'flex';
            chatButton.style.display = 'none';  // Hide the chat button when open
        }
    }

    function closeChat() {
        isOpen = false;
        var chatWindow = document.getElementById('chat-window');
        var chatButton = document.getElementById('chat-button');

        chatWindow.style.display = 'none';
        chatButton.style.display = 'flex';  // Show the chat button again
    }

    function displayMessage(sender, text) {
        var messagesContainer = document.getElementById('chat-messages');
        var messageDiv = document.createElement('div');

        var isUser = sender === 'user';
        messageDiv.style.cssText = `
            max-width: 75%;
            padding: 14px 18px;
            border-radius: ${isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px'};
            align-self: ${isUser ? 'flex-end' : 'flex-start'};
            background: ${isUser ? 'linear-gradient(135deg, ' + primaryColor + ' 0%, ' + darkenColor(primaryColor, 8) + ' 100%)' : 'white'};
            color: ${isUser ? 'white' : '#1a202c'};
            line-height: 1.6;
            font-size: 15px;
            word-wrap: break-word;
            animation: messageSlide 0.3s ease;
            box-shadow: ${isUser ? '0 4px 12px rgba(102, 126, 234, 0.2)' : '0 4px 12px rgba(0, 0, 0, 0.08)'};
            border: ${isUser ? 'none' : '1px solid #e9ecef'};
            position: relative;
            z-index: 1;
        `;

        // Ensure proper UTF-8 text handling and format content
        var formattedContent = text
            // Decode any HTML entities first
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            // Handle numbered lists (1. 2. 3.)
            .replace(/(\d+\.\s)/g, '<br><strong>$1</strong>')
            // Handle bullet points
            .replace(/([•\-\*])\s/g, '<br>$1 ')
            // Double line breaks = paragraph spacing
            .replace(/\n\n+/g, '<br><br>')
            // Single line breaks
            .replace(/\n/g, '<br>')
            // Bold text **text**
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic text *text*
            .replace(/\*([^\*]+)\*/g, '<em>$1</em>')
            // Clean up extra breaks at start
            .replace(/^(<br>)+/, '');

        messageDiv.innerHTML = formattedContent;

        // Add spacing between paragraphs
        var style = document.createElement('style');
        style.textContent = `
            #chat-messages br {
                display: block;
                content: "";
                margin-bottom: 8px;
            }
        `;
        if (!document.getElementById('chat-br-style')) {
            style.id = 'chat-br-style';
            document.head.appendChild(style);
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function showLoadingIndicator() {
        var messagesContainer = document.getElementById('chat-messages');

        var loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-indicator';
        loadingDiv.style.cssText = `
            max-width: 80%;
            padding: 14px 18px;
            border-radius: 20px 20px 20px 4px;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            display: flex;
            gap: 6px;
            align-items: center;
        `;

        // Create 3 animated dots
        for (let i = 0; i < 3; i++) {
            var dot = document.createElement('div');
            dot.style.cssText = `
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #a0aec0;
                animation: dotPulse 1.4s infinite ease-in-out;
                animation-delay: ${i * 0.2}s;
            `;
            loadingDiv.appendChild(dot);
        }

        messagesContainer.appendChild(loadingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function removeLoadingIndicator() {
        var loading = document.getElementById('loading-indicator');
        if (loading) loading.remove();
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
                    displayMessage('bot', data.greeting);
                }
            })
            .catch(error => {
                console.error('Widget greeting error:', error);
                displayMessage('bot', '👋 Hello! How can I help you today?');
            });
    }

    function sendMessage(messageText) {
        var input = document.getElementById('chat-input');
        var message = messageText || input.value.trim();

        if (!message) return;

        if (!messageText) input.value = '';

        displayMessage('user', message);
        showLoadingIndicator();

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
                removeLoadingIndicator();

                if (data.response) {
                    displayMessage('bot', data.response);
                    sessionId = data.session_id;
                } else {
                    displayMessage('bot', '❌ Sorry, something went wrong.');
                }
            })
            .catch(error => {
                removeLoadingIndicator();
                console.error('Widget chat error:', error);
                displayMessage('bot', '❌ Sorry, something went wrong.');
            });
    }

    // Initialize widget when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createWidget);
    } else {
        createWidget();
    }
})();