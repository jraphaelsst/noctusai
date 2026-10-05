/* ===== SCRIPT #26 @314359 attrs= len=6306 */

        // Override para popular aba de fontes no modal de edição
        $(document).ready(function() {
            // Interceptar o evento de abrir modal de edição para buscar fontes
            $('#modal-edit-headline-favorite').on('shown.bs.modal', function() {
                // Sempre ativar a aba "Roteiro" ao abrir o modal
                setTimeout(function() {
                    // Remover active de todas as abas
                    $('#modal-edit-headline-favorite .nav-link').removeClass('active');
                    $('#modal-edit-headline-favorite .tab-pane').removeClass('active show');

                    // Ativar a aba "Roteiro"
                    var $roteiroTab = $('#edit-roadmap-tab');
                    var $roteiroPane = $('#edit-roadmap-content');

                    if ($roteiroTab.length && $roteiroPane.length) {
                        $roteiroTab.addClass('active');
                        $roteiroPane.addClass('active show');

                        // Usar Bootstrap Tab API para garantir ativação
                        var tab = new bootstrap.Tab($roteiroTab[0]);
                        tab.show();
                    }
                }, 50);

                // Esperar um pouco para garantir que o AJAX do headlines.js já terminou
                setTimeout(function() {
                    const headlineId = $('form#headline-favorite-edit').find('input[name="id"]')
                        .val();
                    $('form#headline-favorite-edit')
                        .data('chat-resource-id', headlineId)
                        .data('chat-resource-type', 'eng_reversa_headlines');

                    if (headlineId) {
                        // Buscar dados completos incluindo search_text
                        $.ajax({
                            url: '/dashboard/user/roadmaps/favorites/show-favorites',
                            type: 'POST',
                            data: {
                                _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                                id: headlineId
                            },
                            success: function(data) {
                                // Verificar se há search_text para mostrar a aba de fontes
                                if (data.success && data.search_text && data.search_text.trim() !== '') {
                                    console.log(
                                        'Dados de pesquisa encontrados para modal de edição'
                                    );
                                    // Mostrar a aba de fontes
                                    $('#edit-sources-tab-li').show();

                                    // Formatar e exibir o search_text
                                    let searchTextFormatted = data.search_text.replace(
                                        /\n/g, '<br>');
                                    $('#edit-search-sources-content').html(
                                        searchTextFormatted);
                                } else {
                                    // Esconder a aba de fontes
                                    $('#edit-sources-tab-li').hide();
                                    $('#edit-search-sources-content').html('');
                                }
                            },
                            error: function(xhr) {
                                // Esconder a aba em caso de erro
                                $('#edit-sources-tab-li').hide();
                                $('#edit-search-sources-content').html('');
                            }
                        });
                    }
                }, 800); // Delay para garantir que o headlines.js já carregou os dados
            });

            // Limpar dados ao fechar o modal
            $('#modal-edit-headline-favorite').on('hidden.bs.modal', function() {
                $('#edit-sources-tab-li').hide();
                $('#edit-search-sources-content').html('');
            });

            $('#start_chat_favorite').on('click', function(e) {
                e.preventDefault();
                const resourceId = $('form#headline-favorite-edit').data('chat-resource-id');
                const resourceType = $('form#headline-favorite-edit').data('chat-resource-type');
                window.startChatMode(resourceId, resourceType, this);
            });

            if (typeof window.startChatMode !== 'function') {
                window.startChatMode = function(resourceId, resourceType, buttonElement) {
                    if (!resourceId || !resourceType) {
                        toastr.error('Roteiro não encontrado para iniciar o modo chat.');
                        return;
                    }

                    const $button = $(buttonElement);
                    $button.prop('disabled', true);

                    $.ajax({
                        url: '/dashboard/user/chat/start',
                        method: 'POST',
                        data: {
                            _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                            resource_id: resourceId,
                            resource_type: resourceType
                        },
                        success: function(response) {
                            if (response.success && response.redirect) {
                                window.location.href = response.redirect;
                            } else {
                                toastr.error(response.message ||
                                    'Não foi possível iniciar o modo chat.');
                            }
                        },
                        error: function(xhr) {
                            let message = 'Não foi possível iniciar o modo chat.';
                            if (xhr.responseJSON && xhr.responseJSON.message) {
                                message = xhr.responseJSON.message;
                            }
                            toastr.error(message);
                        },
                        complete: function() {
                            $button.prop('disabled', false);
                        }
                    });
                };
            }
        });
    
