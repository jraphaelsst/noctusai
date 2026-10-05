
        // ✅ V2 SEMPRE USA TEMA DARK (forçado após demo-theme.min.js)
        // Garante que o dark seja aplicado mesmo se o demo-theme.min.js tentar aplicar light
        (function() {
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            document.body.setAttribute('data-bs-theme', 'dark');
        })();
    