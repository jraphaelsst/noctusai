/* ===== SCRIPT #27 @333336 attrs= len=10498 */

        $('body').on('click', '.j_headlines_suggesteds_edit', function() {
            // console.log('Botão de edição clicado!');

            // Limpar campos
            $('form#headline-suggested-edit').find('input[name="id"]').val('');
            $('form#headline-suggested-edit').find('input[name="headline"]').val('');
            $('form#headline-suggested-edit').find('textarea[name="roadmap"]').val('');

            // Esconder campo do roteiro e loading
            $('#roadmap-edit-container').hide();
            $('#roadmap-loading').hide();

            let id = $(this).attr('id');
            let headlineId = $(this).attr('data-headline-id');
            let headline = $(this).attr('data-headline');

            headline = decodeURIComponent(headline);

            // Verificar se o modal existe
            const modal = $('#modal-edit-headline-suggested');

            // Mostrar modal
            if (typeof modal.modal === 'function') {
                modal.modal('show');
            } else {
                console.error('Bootstrap modal não está disponível!');
                // Fallback: mostrar modal manualmente
                modal.show();
            }

            // Sempre ativar a aba "Roteiro" ao abrir o modal
            setTimeout(function() {
                // Remover active de todas as abas
                $('#modal-edit-headline-suggested .nav-link').removeClass('active');
                $('#modal-edit-headline-suggested .tab-pane').removeClass('active show');

                // Ativar a aba "Roteiro"
                var $roteiroTab = $('#edit-roadmap-tab-suggested');
                var $roteiroPane = $('#edit-roadmap-content-suggested');

                if ($roteiroTab.length && $roteiroPane.length) {
                    $roteiroTab.addClass('active');
                    $roteiroPane.addClass('active show');

                    // Usar Bootstrap Tab API para garantir ativação
                    var tab = new bootstrap.Tab($roteiroTab[0]);
                    tab.show();
                }
            }, 150);

            // Preencher campos básicos
            setTimeout(() => {
                $('form#headline-suggested-edit').find('input[name="id"]').val(id);
                $('form#headline-suggested-edit').find('input[name="headline"]').val(headline);
                $('form#headline-suggested-edit')
                    .data('chat-resource-id', headlineId)
                    .data('chat-resource-type', 'eng_reversa_headlines');

                // Buscar headline completa (com roteiro) via AJAX
                $('#roadmap-loading').show();

                $.ajax({
                    url: '/dashboard/user/headlines/suggested/get/' + headlineId,
                    type: 'GET',
                    success: function(data) {
                        $('#roadmap-loading').hide();
                        console.log('Dados recebidos do servidor:', data);

                        // Sempre mostrar o campo do roteiro no modal de edição
                        $('#roadmap-edit-container').show();

                        if (data.success && data.roadmap && data.roadmap.trim() !== '') {
                            // Tem roteiro - preencher o campo
                            console.log('Preenchendo roteiro no campo textarea');
                            $('form#headline-suggested-edit').find('textarea[name="roadmap"]')
                                .val(data.roadmap);
                        } else {
                            // Não tem roteiro - deixar campo vazio
                            console.log('Nenhum roteiro encontrado ou vazio');
                            $('form#headline-suggested-edit').find('textarea[name="roadmap"]')
                                .val('');
                        }

                        // Verificar se há search_text para mostrar a aba de fontes
                        if (data.search_text && data.search_text.trim() !== '') {
                            console.log(
                                'Dados de pesquisa encontrados no roteiro suggested');
                            // Mostrar a aba de fontes
                            $('#edit-sources-tab-li-suggested').show();

                            // Formatar e exibir o search_text
                            let searchTextFormatted = data.search_text.replace(/\n/g,
                                '<br>');
                            $('#edit-search-sources-content-suggested').html(
                                searchTextFormatted);
                        } else {
                            // Esconder a aba de fontes se não houver dados
                            $('#edit-sources-tab-li-suggested').hide();
                            $('#edit-search-sources-content-suggested').html('');
                        }
                    },
                    error: function(xhr) {
                        $('#roadmap-loading').hide();
                        // Sempre mostrar o campo do roteiro, mesmo em caso de erro
                        $('#roadmap-edit-container').show();
                        console.error('Erro ao buscar dados da headline:', xhr);
                        console.error('Response:', xhr.responseText);
                    }
                });
            }, 300);
        })

        $(document).ready(function() {
            // Sempre ativar a aba "Roteiro" ao abrir o modal
            $('#modal-edit-headline-suggested').on('shown.bs.modal', function() {
                setTimeout(function() {
                    // Remover active de todas as abas
                    $('#modal-edit-headline-suggested .nav-link').removeClass('active');
                    $('#modal-edit-headline-suggested .tab-pane').removeClass('active show');

                    // Ativar a aba "Roteiro"
                    var $roteiroTab = $('#edit-roadmap-tab-suggested');
                    var $roteiroPane = $('#edit-roadmap-content-suggested');

                    if ($roteiroTab.length && $roteiroPane.length) {
                        $roteiroTab.addClass('active');
                        $roteiroPane.addClass('active show');

                        // Usar Bootstrap Tab API para garantir ativação
                        var tab = new bootstrap.Tab($roteiroTab[0]);
                        tab.show();
                    }
                }, 50);
            });

            // Limpar dados ao fechar o modal de edição
            $('#modal-edit-headline-suggested').on('hidden.bs.modal', function() {
                $('#edit-sources-tab-li-suggested').hide();
                $('#edit-search-sources-content-suggested').html('');
            });

            // Evento de submit do formulário
            $('#headline-suggested-edit').on('submit', function(e) {
                e.preventDefault();
                // console.log('Formulário submetido!');

                var formData = new FormData(this);
                // console.log('FormData criado:', formData);

                $.ajax({
                    url: '/dashboard/user/headlines/suggested/update',
                    type: 'POST',
                    data: formData,
                    processData: false,
                    contentType: false,
                    success: function(data) {
                        // console.log('Sucesso:', data);
                        if (data.success) {
                            toastr.success(data.message);
                            $('#modal-edit-headline-suggested').modal('hide');
                            window.location.reload();
                        } else {
                            toastr.error(data.message || 'Erro ao atualizar headline');
                        }
                    },
                    error: function(xhr, status, error) {
                        console.error('Erro na requisição:', error);
                        console.error('Status:', status);
                        console.error('Response:', xhr.responseText);
                        toastr.error('Erro ao atualizar headline. Tente novamente.');
                    }
                });
            });

            // Evento de clique no botão de atualização
            $('#update_headline_suggested').on('click', function(e) {
                e.preventDefault();
                $('#headline-suggested-edit').submit();
            });

            $('#start_chat_suggested').on('click', function(e) {
                e.preventDefault();
                const resourceId = $('form#headline-suggested-edit').data('chat-resource-id');
                const resourceType = $('form#headline-suggested-edit').data('chat-resource-type');
                window.startChatMode(resourceId, resourceType, this);
            });
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
                            toastr.error(response.message || 'Não foi possível iniciar o modo chat.');
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
    
