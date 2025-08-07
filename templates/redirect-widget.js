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

        // Create button
        var button = document.createElement("div");
        button.textContent = text;
        button.style.position = "fixed";
        button.style.zIndex = "9999";
        button.style.backgroundColor = color;
        button.style.color = "#fff";
        button.style.padding = "10px 20px";
        button.style.borderRadius = "5px";
        button.style.cursor = "pointer";
        button.style.fontFamily = "Arial, sans-serif";
        button.style.boxShadow = "0 4px 6px rgba(0,0,0,0.1)";
        button.style.fontSize = "14px";

        if (position === "bottom-left") {
            button.style.bottom = "20px";
            button.style.left = "20px";
        } else if (position === "bottom-right") {
            button.style.bottom = "20px";
            button.style.right = "20px";
        }

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
