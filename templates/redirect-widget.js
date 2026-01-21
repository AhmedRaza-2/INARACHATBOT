(function () {
    function init() {
        var currentScript = document.currentScript || (function () {
            var scripts = document.getElementsByTagName('script');
            return scripts[scripts.length - 1];
        })();

        if (!currentScript) {
            console.warn("Redirect widget: script tag not found.");
            return;
        }

        var domain = currentScript.getAttribute("data-domain");
        var redirectUrl = currentScript.getAttribute("data-redirect-url");
        var position = currentScript.getAttribute("data-position") || "bottom-left";
        var color = currentScript.getAttribute("data-color") || "#007bff";
        var text = currentScript.getAttribute("data-text") || "Visit Support";


        // Create button container
        var button = document.createElement("div");
        button.style.position = "fixed";
        button.style.zIndex = "9999";
        button.style.backgroundColor = color;
        button.style.color = "#fff";
        button.style.padding = "12px 20px";
        button.style.borderRadius = "50px";
        button.style.cursor = "pointer";
        button.style.fontFamily = "Arial, sans-serif";
        button.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
        button.style.fontSize = "14px";
        button.style.display = "flex";
        button.style.alignItems = "center";
        button.style.gap = "10px";
        button.style.transition = "all 0.3s ease";

        // Add logo
        var logo = document.createElement("img");
        logo.src = redirectUrl.replace(/\/login.*$/, '') + "/static/logo.png";
        logo.alt = "Logo";
        logo.style.width = "24px";
        logo.style.height = "24px";
        logo.style.borderRadius = "50%";

        // Add text
        var textSpan = document.createElement("span");
        textSpan.textContent = text;

        button.appendChild(logo);
        button.appendChild(textSpan);

        if (position === "bottom-left") {
            button.style.bottom = "20px";
            button.style.left = "20px";
        } else if (position === "bottom-right") {
            button.style.bottom = "20px";
            button.style.right = "20px";
        }

        button.onmouseover = function () {
            this.style.transform = "scale(1.05) translateY(-2px)";
            this.style.boxShadow = "0 6px 16px rgba(0,0,0,0.2)";
        };

        button.onmouseout = function () {
            this.style.transform = "scale(1)";
            this.style.boxShadow = "0 4px 12px rgba(0,0,0,0.15)";
        };

        button.onclick = function () {
            window.location.href = redirectUrl;
        };

        document.body.appendChild(button);
    }

    // Wait for DOM to be ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
