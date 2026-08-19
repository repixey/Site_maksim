(function () {
  const { createApp } = Vue;

  const services = window.__SERVICES__ || [];
  const categories = window.__CATEGORIES__ || [];

  function showToast() {
    const toast = document.getElementById("stub-toast");
    if (!toast) return;
    toast.hidden = false;
    // force reflow so the transition triggers reliably
    void toast.offsetWidth;
    toast.classList.add("is-visible");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toast.classList.remove("is-visible");
      setTimeout(() => { toast.hidden = true; }, 250);
    }, 3200);
  }

  function animateGrid() {
    if (typeof anime === "undefined") return;
    const cards = document.querySelectorAll(".card");
    if (!cards.length) return;
    anime({
      targets: cards,
      opacity: [0, 1],
      translateY: [10, 0],
      delay: anime.stagger(35, { start: 0 }),
      duration: 320,
      easing: "easeOutQuad",
    });
  }

  const app = createApp({
    delimiters: ["[[", "]]"],
    data() {
      return {
        services,
        categories,
        query: "",
        activeCategory: "all",
      };
    },
    computed: {
      filtered() {
        const q = this.query.trim().toLowerCase();
        return this.services.filter((item) => {
          const inCategory =
            this.activeCategory === "all" || item.category === this.activeCategory;
          if (!inCategory) return false;
          if (!q) return true;
          const haystack = `${item.title} ${item.company}`.toLowerCase();
          return haystack.includes(q);
        });
      },
    },
    methods: {
      openStub() {
        showToast();
      },
    },
    updated() {
      this.$nextTick(animateGrid);
    },
    mounted() {
      this.$nextTick(animateGrid);
    },
  });

  app.mount("#app");
})();