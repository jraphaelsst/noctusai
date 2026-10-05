
        (function() {
            // ✅ V2 SEMPRE USA TEMA DARK (forçado como padrão)
            // CÓDIGO ANTERIOR (comentado - respeitava localStorage):
            // const theme = localStorage.getItem('tablerTheme');
            // if (!theme) {
            //     localStorage.setItem('tablerTheme', 'dark');
            //     document.documentElement.classList.add('theme-dark');
            // } else if (theme === 'dark') {
            //     document.documentElement.classList.add('theme-dark');
            // }

            // NOVO CÓDIGO: Força dark sempre na v2
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
        })();
    