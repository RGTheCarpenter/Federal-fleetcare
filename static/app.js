const tabButtons = document.querySelectorAll("[data-tab-target]");
const tabPanels = document.querySelectorAll("[data-tab-section]");

function activateTab(tabName) {
  tabButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tabTarget === tabName);
  });

  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.tabSection === tabName;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  });
}

tabButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    activateTab(button.dataset.tabTarget);
    window.history.pushState({}, "", button.getAttribute("href"));
  });
});

if (tabButtons.length) {
  const activeButton = document.querySelector("[data-tab-target].is-active") || tabButtons[0];
  activateTab(activeButton.dataset.tabTarget);
}
