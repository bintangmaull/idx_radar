chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "fetchAPI") {
        fetch(request.url, request.options)
            .then(response => response.json())
            .then(data => sendResponse({ success: true, data: data }))
            .catch(error => sendResponse({ success: false, error: error.toString() }));
            
        return true; // Menandakan bahwa kita akan merespons secara asinkron
    }
});
