document.addEventListener("DOMContentLoaded", () => {
  const uploadForm = document.getElementById("upload-form");
  const progressBar = document.getElementById("progress-bar");
  const progressText = document.getElementById("progress-text");
  const submitButton = uploadForm.querySelector('button[type="submit"]');
  const viewStatusLink = document.getElementById("view-status-link");
  const downloadsPageLink = document.getElementById("downloads-page-link");

  if (!uploadForm || !progressBar || !progressText || !submitButton) {
    console.error("Required form elements not found!");
    return;
  }

  // Function to update progress display
  function updateProgress(status, progress, message = "") {
    if (progressBar && progressText) {
      progressBar.style.width = `${progress}%`;
      progressBar.setAttribute("aria-valuenow", progress);

      let displayStatus = status;
      if (status === "initializing") {
        displayStatus = "Initializing Task...";
      } else if (status === "processing") {
        displayStatus = message || "Processing..."; // Use message if available
      } else if (status.startsWith("Processing chunk")) {
        displayStatus = status; // Show chunk progress directly
      } else if (status === "Concatenating audio files...") {
        displayStatus = "Concatenating Audio...";
      } else if (status === "Completed") {
        displayStatus = "Processing Complete!";
      } else if (status === "Failed") {
        displayStatus = `Error: ${message || "Unknown error"}`;
        progressBar.classList.add("bg-danger");
      } else {
        displayStatus = status; // Default display
      }

      progressText.textContent = `${displayStatus} (${progress}%)`;

      if (progress < 100 && status !== "Failed") {
        progressBar.classList.remove("bg-success", "bg-danger");
        progressBar.classList.add(
          "progress-bar-animated",
          "progress-bar-striped"
        );
        submitButton.disabled = true;
        submitButton.textContent = "Processing...";
      } else {
        progressBar.classList.remove(
          "progress-bar-animated",
          "progress-bar-striped"
        );
        submitButton.disabled = false;
        submitButton.textContent = "Convert"; // Reset button text
        if (status === "Completed") {
          progressBar.classList.add("bg-success");
        } else if (status !== "Failed") {
          // Keep default color if 100% but not explicitly completed or failed yet
        }
      }
      // Show status/download links when processing starts or finishes
      if (viewStatusLink) viewStatusLink.style.display = "inline";
      if (downloadsPageLink) downloadsPageLink.style.display = "inline";
    }
  }

  // Function to poll for progress
  function pollProgress(taskId) {
    const pollInterval = 3000; // Poll every 3 seconds
    let pollTimer;

    function checkStatus() {
      console.log(`Checking progress for task: ${taskId}`); // Debug log
      fetch(`/progress/${taskId}`)
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          console.log("Progress data received:", data); // Debug log

          // Update UI
          const status = data.status || "Unknown";
          const progress = data.progress || 0;
          const message = data.message || data.error || ""; // Use error as message if present

          updateProgress(status, progress, message);

          // Check if task is completed or failed
          if (
            status.toLowerCase() === "completed" ||
            status.toLowerCase() === "failed" ||
            status.startsWith("Warning")
          ) {
            clearInterval(pollTimer); // Stop polling
            console.log(
              `Polling stopped for task ${taskId}. Status: ${status}`
            );

            if (status.toLowerCase() === "completed") {
              // Determine file type from form or response if possible
              // Assuming 'audio' for now as per primary use case
              const fileType = "audio";
              // Trigger download
              console.log(
                `Attempting to download ${fileType} for task ${taskId}`
              );
              window.location.href = `/download/${taskId}/${fileType}`;
            } else {
              // Handle failure or warning - maybe show error message more prominently
              console.error(
                `Task ${taskId} ended with status: ${status}. Error: ${message}`
              );
              updateProgress(
                status,
                progress,
                `Task ended with status: ${status}. ${
                  message ? "Details: " + message : ""
                }`
              );
            }
            submitButton.disabled = false; // Re-enable button
            submitButton.textContent = "Convert"; // Reset button text
          }
        })
        .catch((error) => {
          console.error("Polling error:", error);
          updateProgress("Error", 0, "Could not retrieve progress.");
          clearInterval(pollTimer); // Stop polling on error
          submitButton.disabled = false; // Re-enable button
          submitButton.textContent = "Convert"; // Reset button text
        });
    }

    // Initial check and start interval
    checkStatus();
    pollTimer = setInterval(checkStatus, pollInterval);
  }

  // Form submission handler
  uploadForm.addEventListener("submit", (event) => {
    event.preventDefault(); // Prevent default form submission

    submitButton.disabled = true;
    submitButton.textContent = "Uploading...";
    updateProgress("Uploading", 0); // Initial progress update

    const formData = new FormData(uploadForm);

    fetch("/", {
      // Submit to the root endpoint
      method: "POST",
      body: formData,
    })
      .then((response) => {
        if (!response.ok) {
          // Try to get error message from response body
          return response
            .json()
            .then((errData) => {
              throw new Error(
                errData.error || `HTTP error! status: ${response.status}`
              );
            })
            .catch(() => {
              // Fallback if response body is not JSON or parsing fails
              throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
      })
      .then((data) => {
        if (data.task_id) {
          console.log("Task ID received:", data.task_id); // Debug log
          updateProgress("Initializing", 0); // Update status
          pollProgress(data.task_id); // Start polling
        } else {
          throw new Error(data.error || "No task ID received from server.");
        }
      })
      .catch((error) => {
        console.error("Form submission error:", error);
        updateProgress("Error", 0, `Submission failed: ${error.message}`);
        submitButton.disabled = false; // Re-enable button
        submitButton.textContent = "Convert"; // Reset button text
      });
  });
});

// Add simple flash message handling (optional, requires Bootstrap JS/CSS)
document.addEventListener("DOMContentLoaded", () => {
  const flashMessages = document.querySelectorAll(".alert");
  flashMessages.forEach((flash) => {
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (bootstrap && bootstrap.Alert) {
        const alertInstance = bootstrap.Alert.getOrCreateInstance(flash);
        if (alertInstance) {
          alertInstance.close();
        }
      } else {
        flash.style.display = "none"; // Fallback if Bootstrap JS is not loaded
      }
    }, 5000);
  });
});
