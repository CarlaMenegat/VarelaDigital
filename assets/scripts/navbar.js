document.addEventListener("DOMContentLoaded", () => {
  const currentPath = window.location.pathname.split("/").pop() || "index.html";

  // Limpa estados anteriores
  document.querySelectorAll(".nav-link").forEach(el => {
    el.classList.remove("active");
    el.removeAttribute("aria-current");
  });

  document.querySelectorAll(".dropdown-item").forEach(el => {
    el.classList.remove("is-current");
  });

  // Verifica todos os links
  document.querySelectorAll(".nav-link, .dropdown-item").forEach(link => {
    const href = link.getAttribute("href");
    if (!href) return;

    const target = href.split("/").pop();

    if (target === currentPath) {

      if (link.classList.contains("dropdown-item")) {
        // Marca item do dropdown com classe custom
        link.classList.add("is-current");

        // Marca o toggle do dropdown como ativo
        const dropdown = link.closest(".dropdown");
        if (dropdown) {
          const toggle = dropdown.querySelector(".nav-link");
          if (toggle) {
            toggle.classList.add("active");
            toggle.setAttribute("aria-current", "page");
          }
        }

      } else {
        // Nav-link normal
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      }
    }
  });
});