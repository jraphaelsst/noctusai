
        async function saveVariablesAjax() {
            const button = event.target.closest('button');
            const btnText = button.querySelector('.btn-text');
            const spinner = button.querySelector('.spinner-border');

            const hasPendingItems = Object.values(window.pendingVariables || {}).some(items => items.length > 0);

            if (!hasPendingItems) {
                toastr.info('Nenhum item para salvar.');
                return;
            }

            button.disabled = true;
            btnText.textContent = 'Salvando...';
            spinner.classList.remove('d-none');

            try {
                const form = document.getElementById('save-variables');
                const formData = new FormData(form);

                const response = await fetch('/dashboard/user/searches/save', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute(
                            'content')
                    }
                });

                const data = await response.json();

                if (response.ok) {
                    toastr.success('Variáveis atualizadas com sucesso!');

                    const modal = bootstrap.Modal.getInstance(document.getElementById('addVariableModal'));
                    if (modal) {
                        modal.hide();
                    }

                    window.pendingVariables = {};

                    document.querySelectorAll('.pending-new-item').forEach(item => {
                        item.remove();
                    });

                    const saveButton = document.getElementById('save-unsaved-variables-btn');
                    if (saveButton) {
                        saveButton.classList.add('d-none');
                    }

                    const alert = document.getElementById('pending-variables-alert');
                    if (alert) {
                        alert.style.display = 'none';
                    }

                    const activeTab = document.querySelector('.tab-pane.active[data-type]');
                    if (activeTab) {
                        const type = activeTab.getAttribute('data-type');
                        if (type === 'unified') {
                            if (typeof loadUnifiedData === 'function') {
                                window._unifiedLoading = false;
                                await loadUnifiedData();
                            }
                        } else {
                            const loading = document.getElementById('global-variables-loading');
                            const content = document.getElementById('variables-content');

                            if (loading) loading.style.display = 'flex';
                            if (content) content.style.display = 'none';

                            await loadTabVariables(type);

                            if (loading) loading.style.display = 'none';
                            if (content) content.style.display = 'block';
                        }
                    }

                } else {
                    if (data.errors) {
                        Object.values(data.errors).forEach(error => {
                            toastr.error(error);
                        });
                    } else {
                        toastr.error(data.message || 'Erro ao salvar variáveis.');
                    }
                }

            } catch (error) {
                console.error('Erro:', error);
                toastr.error('Erro ao processar a solicitação.');
            } finally {
                button.disabled = false;
                btnText.textContent = 'Salvar Alterações';
                spinner.classList.add('d-none');
            }
        }

        function openRemoveModal(id) {
            const confirmBtn = document.getElementById('viral_topic_remove_confirm');
            if (confirmBtn) {
                confirmBtn.setAttribute('data-id', id);
            }
        }

        // Função removida daqui - movida para o início do script para garantir disponibilidade

        function updateViralPendingCounter() {
            const pendingItemsContainer = document.getElementById('pending-items');
            if (!pendingItemsContainer) return;

            // Buscar apenas itens que estão visíveis (não têm display: none)
            const allItems = pendingItemsContainer.querySelectorAll('.pending-item-container');
            const remainingItems = Array.from(allItems).filter(item => {
                const style = window.getComputedStyle(item);
                return style.display !== 'none' && style.visibility !== 'hidden' && item.offsetParent !== null;
            });

            const counterBadge = document.querySelector('a[href="#tab-pending-viral-topics"] .badge');

            if (remainingItems.length === 0) {
                if (counterBadge) {
                    counterBadge.remove();
                }
            } else {
                if (counterBadge) {
                    counterBadge.textContent = remainingItems.length;
                } else {
                    // Criar badge se não existir
                    const tabLink = document.querySelector('a[href="#tab-pending-viral-topics"]');
                    if (tabLink) {
                        const newBadge = document.createElement('span');
                        newBadge.className = 'badge bg-yellow ms-1';
                        newBadge.textContent = remainingItems.length;
                        tabLink.appendChild(newBadge);
                    }
                }
            }
        }

        function addViralToApprovedList(viralTopic) {
            const approvedContainer = document.getElementById('viral-topics-badges');
            if (!approvedContainer) return;

            if (approvedContainer.innerHTML.trim() === '') {
                approvedContainer.innerHTML = '';
            }

            const isManual = !viralTopic.eng_reversa_result_id || viralTopic.eng_reversa_result_id == 0;
            const badgeClass = isManual ? 'viral-topic-badge-manual' : 'viral-topic-badge';

            const totalPlays = viralTopic.total_plays || 0;
            let viewsHtml = '';
            if (isManual) {
                viewsHtml = '<span class="viral-topic-views">Manual</span>';
            } else if (totalPlays > 0) {
                const formatted = formatViralNumberWithSuffix(totalPlays);
                viewsHtml = `<span class="viral-topic-views">${formatted} Views</span>`;
            }

            const newBadge = document.createElement('span');
            newBadge.className = `${badgeClass} flex-grow-1 text-center badge-topic`;
            newBadge.title = 'Clique para ver os virais';
            newBadge.style.cursor = 'pointer';
            newBadge.onclick = function() {
                openViralModal(viralTopic.id, viralTopic.topic);
            };
            newBadge.innerHTML = `
                ${viralTopic.topic}
                ${viewsHtml}
                <button
                    type="button"
                    class="btn-close btn-close-white ms-auto viral-topic-remove-btn"
                    aria-label="Remover"
                    style="font-size: 0.7em;"
                    data-bs-toggle="modal"
                    data-bs-target="#modal-remove-topic"
                    data-id="${viralTopic.id}"
                    onclick="event.stopPropagation(); openRemoveModal(${viralTopic.id});"></button>
            `;

            approvedContainer.insertBefore(newBadge, approvedContainer.firstChild);

            newBadge.style.opacity = '0';
            newBadge.style.transform = 'scale(0.8)';
            setTimeout(() => {
                newBadge.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                newBadge.style.opacity = '1';
                newBadge.style.transform = 'scale(1)';
            }, 10);
        }

        function formatViralNumberWithSuffix(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
            }
            return num.toString();
        }

        function removeViralTopic(id) {
            const clickedBadge = document.querySelector(`[onclick*="openViralModal(${id},"]`);
            let topicName = null;

            if (clickedBadge) {
                const onclickAttr = clickedBadge.getAttribute('onclick');
                const match = onclickAttr.match(/openViralModal\(\d+,\s*'([^']+)'\)/);
                if (match) {
                    topicName = match[1];
                }
            }

            // Fechar o modal
            const modalElement = document.getElementById('modal-remove-topic');
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.hide();
            }

            $.ajax({
                url: `dashboard/user/searches/viral/topics/remove/${id}`,
                method: 'GET',
                headers: {
                    'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
                },
                success: function(data) {
                    if (data.success) {
                        toastr.success(data.message);

                        // Remove TODOS os badges com o mesmo nome do tópico
                        if (topicName) {
                            const badges = document.querySelectorAll('.badge-topic');

                            badges.forEach(badge => {
                                const onclickAttr = badge.getAttribute('onclick');
                                if (onclickAttr && onclickAttr.includes(`'${topicName}'`)) {
                                    badge.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                                    badge.style.opacity = '0';
                                    badge.style.transform = 'scale(0.8)';

                                    setTimeout(() => {
                                        badge.remove();

                                        // Verifica se não há mais badges
                                        const remainingBadges = document.querySelectorAll(
                                            '.badge-topic');
                                        const visibleBadges = Array.from(remainingBadges)
                                            .filter(b =>
                                                !b.classList.contains('d-none')
                                            );

                                        if (visibleBadges.length === 0) {
                                            const container = document.getElementById(
                                                'viral-topics-badges');
                                            if (container && container.children.length === 0) {
                                                container.innerHTML = '';
                                            }
                                        }
                                    }, 300);
                                }
                            });
                        }
                    } else {
                        toastr.error(data.message);
                    }
                },
                error: function(err) {
                    console.error('Erro na requisição:', err);
                    toastr.error('Erro ao processar a solicitação.');
                }
            });
        }
    