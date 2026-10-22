document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("emailDetail");
  const emailId = container.getAttribute("data-email-id");
  const toggleBtn = document.getElementById("toggleReadBtn");

  toggleBtn.addEventListener("click", async () => {
    const currentlyMarkedUnread = toggleBtn.textContent.trim() === "Mark as Read";
    const newIsRead = currentlyMarkedUnread;

    toggleBtn.disabled = true;
    const response = await apiFetch(`/emails/${emailId}/read`, {
      method: "PATCH",
      body: JSON.stringify({ is_read: newIsRead }),
    });
    toggleBtn.disabled = false;
    if (!response || !response.ok) return;

    const data = await response.json();
    toggleBtn.textContent = data.is_read ? "Mark as Unread" : "Mark as Read";
    if (window.parent !== window) window.parent.postMessage({ type: "emailorbit-updated" }, window.location.origin);
  });

  // Phase 9: clicking a smart reply chip copies its text to the
  // clipboard so the user can paste it into Gmail's own reply box —
  // this app only suggests replies, it doesn't send mail on its own.
  document.querySelectorAll(".smart-reply-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const text = chip.getAttribute("data-reply-text");
      try {
        await navigator.clipboard.writeText(text);
        const original = chip.textContent;
        chip.textContent = "Copied!";
        setTimeout(() => {
          chip.textContent = original;
        }, 1200);
      } catch (err) {
        // Clipboard API can be unavailable (e.g. insecure context) —
        // fail silently rather than breaking the page.
      }
    });
  });

  // Phase 10: personalization — picking a value here immediately
  // corrects this email's category/priority (rule #20's UserFeedback
  // record) rather than waiting on a future model retrain.
  const feedbackStatus = document.getElementById("feedbackStatus");

  async function submitFeedback(feedbackType, correctedValue) {
    feedbackStatus.textContent = "Saving…";
    const response = await apiFetch(`/emails/${emailId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback_type: feedbackType, corrected_value: correctedValue,
        apply_to_sender: document.getElementById("applyToSender").checked }),
    });
    if (!response || !response.ok) {
      feedbackStatus.textContent = "Could not save correction.";
      return;
    }
    feedbackStatus.textContent = "Saved — thanks!";
    document.getElementById(feedbackType === "category" ? "categoryBadge" : "priorityBadge").textContent = correctedValue;
    if (feedbackType === "priority") document.getElementById("priorityBadge").className = `badge badge-priority-${correctedValue}`;
    if (window.parent !== window) window.parent.postMessage({ type: "emailorbit-updated" }, window.location.origin);
  }

  const categorySelect = document.getElementById("categoryCorrection");
  if (categorySelect) {
    categorySelect.addEventListener("change", (e) => {
      if (!e.target.value) return;
      submitFeedback("category", e.target.value);
    });
  }

  const prioritySelect = document.getElementById("priorityCorrection");
  if (prioritySelect) {
    prioritySelect.addEventListener("change", (e) => {
      if (!e.target.value) return;
      submitFeedback("priority", e.target.value);
    });
  }
});
