/* ===== SCRIPT #36 @692506 attrs= len=6342 */

        // Função para ajustar altura
        function adjustTextareaHeight(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = (textarea.scrollHeight) + 'px';
        }

        // Função para ajustar todos os textareas
        function adjustAllTextareas() {
            document.querySelectorAll('.auto-resize').forEach(function(textarea) {
                adjustTextareaHeight(textarea);
            });
        }

        // Ajusta imediatamente após o DOM carregar
        document.addEventListener('DOMContentLoaded', function() {
            // Ajusta inicialmente
            adjustAllTextareas();
            //$(".thinkForMe").css("display", "none");

            // Ajusta após um pequeno delay para garantir que todo conteúdo foi carregado
            setTimeout(adjustAllTextareas, 100);

            // Adiciona listeners para eventos
            document.querySelectorAll('.auto-resize').forEach(function(textarea) {
                textarea.addEventListener('input', function() {
                    adjustTextareaHeight(this);
                });

                textarea.addEventListener('focus', function() {
                    adjustTextareaHeight(this);
                });
            });
        });

        // Ajusta quando a janela é redimensionada
        window.addEventListener('resize', adjustAllTextareas);

        // Ajusta quando o conteúdo é modificado dinamicamente
        const observer = new MutationObserver(function(mutations) {
            adjustAllTextareas();
        });

        // Observa mudanças no documento
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });

        // Inicializar TomSelects para as opções avançadas
        function initializeAdvancedTomSelects() {
            if (window.TomSelect) {
                if(!window.tomSelects) {
                    window.tomSelects = window.tomSelects || {};
                }
                // TomSelect para nichos
                if (!window.tomSelects || !window.tomSelects['make-headlines-niches']) {
                    const nichesEl = document.getElementById('make-headlines-niches');
                    if (nichesEl && !nichesEl.tomselect) {
                        window.tomSelects = window.tomSelects || {};
                        window.tomSelects['make-headlines-niches'] = new TomSelect(nichesEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para profissões
                if (!window.tomSelects || !window.tomSelects['make-headlines-professions']) {
                    const professionsEl = document.getElementById('make-headlines-professions');
                    if (professionsEl && !professionsEl.tomselect) {
                        window.tomSelects['make-headlines-professions'] = new TomSelect(professionsEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para formatos de vídeo
                if (!window.tomSelects || !window.tomSelects['make-headlines-format-videos']) {
                    const formatVideosEl = document.getElementById('make-headlines-format-videos');
                    if (formatVideosEl && !formatVideosEl.tomselect) {
                        window.tomSelects['make-headlines-format-videos'] = new TomSelect(formatVideosEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

                // TomSelect para gatilhos de atenção
                if (!window.tomSelects || !window.tomSelects['make-headlines-attention-triggers']) {
                    const attentionTriggersEl = document.getElementById('make-headlines-attention-triggers');
                    if (attentionTriggersEl && !attentionTriggersEl.tomselect) {
                        window.tomSelects['make-headlines-attention-triggers'] = new TomSelect(attentionTriggersEl, {
                            copyClassesToDropdown: false,
                            dropdownParent: 'body',
                            create: false,
                            render: {
                                option: function(data, escape) {
                                    return `<div class="option">${escape(data.text)}</div>`;
                                }
                            }
                        });
                    }
                }

            }
        }

        // Inicializar TomSelects quando o modal for aberto
        document.addEventListener('DOMContentLoaded', function() {
            // Inicializar imediatamente
            initializeAdvancedTomSelects();

            // Inicializar quando as opções avançadas forem mostradas
            document.addEventListener('click', function(e) {
                if (e.target && e.target.id === 'set_headlines_categories') {
                    setTimeout(function() {
                        initializeAdvancedTomSelects();
                    }, 300); // Aguardar a animação do toggle
                }
            });
        });
    
