document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".compose-suggestion").forEach(button => {
    button.addEventListener("click", () => {
      const body = document.getElementById("composeBody");
      // Preserve anything already typed; the user can edit the inserted text.
      body.value += (body.value ? "\n\n" : "") + button.dataset.text;
      body.focus();
    });
  });
  document.querySelectorAll(".delivery-form").forEach(form => {
    form.addEventListener("submit", () => {
      document.querySelectorAll(".delivery-form button").forEach(button => { button.disabled = true; });
    });
  });
});
