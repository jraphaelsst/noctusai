$('form#make_roadmap').submit(function(e){
    "use strict";
    e.preventDefault();

    $('#button_make_roadmap').prop('disabled', true);
    $('#button_make_roadmap').text('Gerando roteiro...');

    var formData = new FormData(this);

    // var formData = new FormData(this);
    // //var formData = new FormData(document.getElementById('form-customer-headlines'));
    // // Cria o FormData a partir de outro formulário
    // var formDataHeadlineSelected = new FormData(document.getElementById('form-customer-headlines'));

    // // Adiciona os dados do segundo formulário ao primeiro
    // for (var pair of formDataHeadlineSelected.entries()) {
    //     formData.append(pair[0], pair[1]);
    // }

    $.ajax({
        type: "post",
        url: 'dashboard/user/roadmaps/store',
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#button_make_roadmap').prop('disabled', false);
                $('#button_make_roadmap').html('[SVG]\n'+
                    '                            Gerar Roteiro');
            }
            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.success){
                $('#modal-show-roadmaps').modal('show');

                startProgressCheckRoadmaps(data.roadmap_ids);
            }
            if(data.reset){
                $('#customer-headlines-edit')[0].reset();
                $('#customer-headlines-select-structures')[0].tomselect.clear();
            }
            if(data.modalOut){
                $('#modal-customer-headline-make_roadmap').modal('hide');
            }

        },
        error: function(data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao gerar o roteiro.');
            }

            $('#button_make_roadmap').prop('disabled', false);
            $('#button_make_roadmap').html('[SVG]\n'+
                '                            Gerar Roteiro');
        }
    });
    return false;
});

function startProgressCheckRoadmaps(roadmap_ids){

    const contRoadmaps = roadmap_ids.length;

    const interval = setInterval(function(){

        $.ajax({
            type: "post",
            url: "/dashboard/user/roadmaps/check-progress",
            data: {
                roadmap_ids: roadmap_ids
            },
            success: function(data){
                if(data.roadmapsSuccess.length == contRoadmaps){
                    clearInterval(interval);

                    if(data.roadmapsSuccess.length > 1){
                        $('.j_change_modal_size').removeClass('modal-lg');
                        $('.j_change_modal_size').addClass('modal-xl');
                        let templateHtml = '';
                        let cont = 1;
                        templateHtml += '<div class="row">';
                        data.roadmapsSuccess.forEach(function(roadmap){
                            templateHtml += `

                                    <div class="col-6">
                                        <h2 class="mb-3">Opção ${cont}</h2>
                                        <div class="accordion accordion-tabs">
                                            <div class="accordion-item">
                                                <div class="accordion-collapse collapse show pt-4">
                                                    <div class="accordion-body pt-0">
                                                        <div>
                                                        <p>
                                                            ${roadmap.roadmap_content.replace(/\n/g, '<br>')}
                                                        </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <a href="dashboard/user/roadmaps?open_id=${roadmap.id}" id="go_to_roadmap" href="javascript:;" class="btn btn-primary ms-auto">[SVG]
                                            Ir para o Roteiro</a>
                                    </div>

                            `;
                            cont++;
                        });
                        templateHtml += '</div>';
                        $('.preload_roadmaps').html(templateHtml);
                    }else{
                        $('.j_change_modal_size').removeClass('modal-xl');
                        $('.j_change_modal_size').addClass('modal-lg');
                        let templateHtml = '';
                        let cont = 1;
                        templateHtml += '<div class="row">';
                        data.roadmapsSuccess.forEach(function(roadmap){
                            templateHtml += `

                                    <div class="col-12">
                                        <div class="accordion accordion-tabs">
                                            <div class="accordion-item">
                                                <div class="accordion-collapse collapse show pt-4">
                                                    <div class="accordion-body pt-0">
                                                        <div>
                                                        <p>
                                                            ${roadmap.roadmap_content.replace(/\n/g, '<br>')}
                                                        </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <a href="dashboard/user/roadmaps?open_id=${roadmap.id}" id="go_to_roadmap" href="javascript:;" class="btn btn-primary ms-auto">[SVG]
                                            Ir para o Roteiro</a>
                                    </div>

                            `;
                            cont++;
                        });
                        templateHtml += '</div>';
                        $('.preload_roadmaps').html(templateHtml);
                    }

                }
            }
        });
    }, 5000);
}

if($('form#make_roadmap select#customer-headlines-select-headline').length > 0){
    $('form#make_roadmap select#customer-headlines-select-headline').on('change', function(){
        let headlineId = $(this).val();
        let structure_id = this.selectedOptions[0].dataset.structureId;
        let headline = this.selectedOptions[0].dataset.headline;

        $('form#make_roadmap').find('input[name="headline_id"]').remove();
        $('form#make_roadmap').find('input[name="structure_id"]').remove();
        $('form#make_roadmap').find('input[name="headline"]').remove();

        $('form#make_roadmap').append('<input type="hidden" name="headline_id" value="'+headlineId+'">');
        $('form#make_roadmap').append('<input type="hidden" name="structure_id" value="'+structure_id+'">');
        $('form#make_roadmap').append('<input type="hidden" name="headline" value="'+headline+'">');
    });
}

// Pega os parâmetros da URL
const params = new URLSearchParams(window.location.search);

// Verifica se existe o parâmetro 'open_id'
if (params.has('open_id')) {
    setTimeout(function(){
    let open_id = params.get('open_id');
        let button_view = $('.j_roadmaps_view[id="'+open_id+'"]');
        button_view.click();
    }, 2500);
}

// Inicialização do Quill uma única vez fora do evento de click
var quill = new Quill('#quill-editor', {
    theme: 'snow',
    placeholder: 'Digite seu texto aqui...',
    modules: {
        toolbar: [
            ['bold', 'italic', 'underline'],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            ['clean']
        ]
    }
});

// Função para converter HTML para Markdown
function htmlToMarkdown(html) {
    if (!html) return '';

    // Cria um elemento temporário para processar o HTML
    var tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;

    // Função recursiva para processar os nós
    function processNode(node, listDepth) {
        listDepth = listDepth || 0;

        if (node.nodeType === 3) { // Text node
            return node.textContent;
        }

        if (node.nodeType === 1) { // Element node
            var tagName = node.tagName ? node.tagName.toLowerCase() : '';
            var children = Array.from(node.childNodes);

            switch(tagName) {
                case 'strong':
                case 'b':
                    var content = children.map(function(n) { return processNode(n, listDepth); }).join('');
                    return '**' + content + '**';
                case 'em':
                case 'i':
                    var content = children.map(function(n) { return processNode(n, listDepth); }).join('');
                    return '*' + content + '*';
                case 'u':
                    var content = children.map(function(n) { return processNode(n, listDepth); }).join('');
                    return '__' + content + '__';
                case 'p':
                    var content = children.map(function(n) { return processNode(n, listDepth); }).join('').trim();
                    return content ? content + '\n\n' : '';
                case 'br':
                    return '\n';
                case 'ol':
                    var olItems = Array.from(node.querySelectorAll(':scope > li'));
                    return olItems.map(function(li, index) {
                        var indent = '  '.repeat(listDepth);
                        var content = processNode(li, listDepth + 1).trim();
                        return indent + (index + 1) + '. ' + content;
                    }).join('\n') + '\n';
                case 'ul':
                    var ulItems = Array.from(node.querySelectorAll(':scope > li'));
                    return ulItems.map(function(li) {
                        var indent = '  '.repeat(listDepth);
                        var content = processNode(li, listDepth + 1).trim();
                        return indent + '- ' + content;
                    }).join('\n') + '\n';
                case 'li':
                    var parts = [];
                    for (var i = 0; i < children.length; i++) {
                        var child = children[i];
                        if (child.nodeType === 1) {
                            var childTag = child.tagName ? child.tagName.toLowerCase() : '';
                            if (childTag === 'ul' || childTag === 'ol') {
                                parts.push('\n' + processNode(child, listDepth));
                            } else {
                                parts.push(processNode(child, listDepth));
                            }
                        } else {
                            parts.push(processNode(child, listDepth));
                        }
                    }
                    return parts.join('').trim();
                default:
                    return children.map(function(n) { return processNode(n, listDepth); }).join('');
            }
        }

        return '';
    }

    var markdown = processNode(tempDiv).trim();
    // Limpa múltiplas quebras de linha consecutivas (máximo 2)
    markdown = markdown.replace(/\n{3,}/g, '\n\n');
    return markdown;
}

// Intercepta o evento de cópia para converter HTML para Markdown
// O Quill cria um elemento .ql-editor dentro do #quill-editor
var quillEditorElement = quill.root;
if (quillEditorElement) {
    quillEditorElement.addEventListener('copy', function(e) {
        try {
            // Obtém a seleção atual do Quill
            var selection = quill.getSelection(true);

            if (selection && selection.length > 0) {
                // Obtém o conteúdo Delta da seleção
                var delta = quill.getContents(selection.index, selection.length);

                // Converte Delta para HTML usando um Quill temporário
                var tempDiv = document.createElement('div');
                var tempQuill = new Quill(tempDiv, {
                    theme: 'snow',
                    modules: { toolbar: false }
                });
                tempQuill.setContents(delta);
                var html = tempDiv.querySelector('.ql-editor').innerHTML;

                // Converte HTML para Markdown
                var markdownContent = htmlToMarkdown(html);

                // Substitui o conteúdo no clipboard
                if (e.clipboardData) {
                    e.clipboardData.setData('text/plain', markdownContent);
                    e.clipboardData.setData('text/html', html);
                    e.preventDefault();
                } else if (window.clipboardData) {
                    // Fallback para IE
                    window.clipboardData.setData('Text', markdownContent);
                    e.preventDefault();
                }
            }
        } catch (err) {
            console.error('Erro ao converter para markdown:', err);
            // Se houver erro, deixa o comportamento padrão
        }
    });
}

// Botão para copiar o conteúdo do roteiro
$(document).on('click', '#btn-copy-roadmap', function() {
    // Obtém o texto puro do editor Quill (sem HTML)
    var content = quill.getText();

    // Remove espaços em branco no início e fim
    content = content.trim();

    if (!content) {
        toastr.warning('Nada para copiar! O roteiro está vazio.');
        return;
    }

    // Usa a API moderna de clipboard
    if (navigator.clipboard) {
        navigator.clipboard.writeText(content).then(function() {
            toastr.success('Roteiro copiado com sucesso!');
        }).catch(function(err) {
            console.error('Erro ao copiar: ', err);
            toastr.error('Não foi possível copiar o conteúdo.');
        });
    } else {
        // Fallback para navegadores antigos
        var $tempInput = $('<textarea>');
        $('body').append($tempInput);
        $tempInput.val(content).select();
        try {
            document.execCommand('copy');
            toastr.success('Roteiro copiado com sucesso!');
        } catch (err) {
            toastr.error('Não foi possível copiar o conteúdo.');
        }
        $tempInput.remove();
    }
});

// Mensagem do feedback do roadmap
var feedbackMessage = {
    liked: "Que bom que você gostou! 🎉  Sua opinião nos ajuda a continuar melhorando. 😊",
    disliked: "Obrigado pelo seu feedback! 🙏  Vamos trabalhar para melhorar sua experiência."
};
// Evento de click apenas atualiza o conteúdo
$(document).on('click', '.j_roadmaps_view', function () {
    var id = $(this).attr('id');

    $('.j_roadmap_payload').html('')

    // Esconder a aba de fontes por padrão ao abrir o modal - usar CSS inline para garantir
    var $tabSearchSources = $('#tab-search-sources');
    $tabSearchSources.css('display', 'none');
    $tabSearchSources.attr('style', 'display: none !important');
    $tabSearchSources.hide();
    $('#search-sources-content').html('');

    $.ajax({
        type: 'get',
        url: 'dashboard/user/roadmaps/view/'+id,
        dataType: 'json',
        success: function (data) {
            if (data.success) {
                // Esconder a aba de fontes antes de verificar - usar CSS inline para garantir
                var $tabSearchSources = $('#tab-search-sources');
                $tabSearchSources.css('display', 'none');
                $tabSearchSources.attr('style', 'display: none !important');
                $tabSearchSources.hide();
                $('#search-sources-content').html('');

                $('#modal-customer-roadmap-edit-roadmap').modal('show')

                // Sempre ativar a aba "Roteiro" ao abrir o modal
                setTimeout(function() {
                    // Remover active de todas as abas
                    $('#modal-customer-roadmap-edit-roadmap .nav-link').removeClass('active');
                    $('#modal-customer-roadmap-edit-roadmap .tab-pane').removeClass('active show');

                    // Ativar a aba "Roteiro"
                    var $roteiroTab = $('#modal-customer-roadmap-edit-roadmap a[href="#roadmap_finale"]');
                    var $roteiroPane = $('#roadmap_finale');

                    $roteiroTab.addClass('active');
                    $roteiroPane.addClass('active show');

                    // Usar Bootstrap Tab API para garantir ativação
                    var tab = new bootstrap.Tab($roteiroTab[0]);
                    tab.show();
                }, 100);

                var $editForm = $('form#form-customer-roadmaps-edit');
                $editForm.find('input[name=name]').val(data.name)
                $editForm.find('input[name=id]').val(id)
                $editForm
                    .data('chat-resource-id', id)
                    .data('chat-resource-type', 'user_roadmaps');
                $('form#form-roadmap-reprocess input[name=id]').val(id)

                window.currentRoadmapViewData = data;

                //Payload
                // Formata o JSON para uma string bem formatada
                let formattedPayload = JSON.stringify(data.payload, null, 2); // '2' adiciona o espaçamento
                let formattedParams = (data.params != null) ? JSON.stringify(data.params, null, 2) : '{}';

                //Substitui as quebras de linha por <br> e preserva o conteúdo
                formattedPayload = formattedPayload.replace(/\\r/g, '\r').replace(/\\n/g, '\n');

                $('.j_roadmap_payload').html('<pre>' + Prism.highlight(formattedPayload, Prism.languages.json, 'json') + '</pre>'); // Exibe o JSON formatado

                // Atualiza o Quill: texto bruto (setText) evita espaçamento duplo; se já for HTML (após edição), usa innerHTML
                var roadmapContent = data.roadmap_gpt || '';
                if (roadmapContent.indexOf('<') !== -1) {
                    quill.root.innerHTML = roadmapContent;
                } else if (typeof quill.setText === 'function') {
                    quill.setText(roadmapContent);
                } else {
                    quill.root.innerHTML = roadmapContent;
                }
                document.getElementById('roadmap_gpt').value = roadmapContent;
                $("#roadmap-feedback-btn-liked, #roadmap-feedback-btn-disliked").attr('roadmap_id', id);
                console.log(data.roadmap_liked)
                if(data.roadmap_liked === 0){
                    $('#feedback-section').show();
                    $('#feedback-message').hide();
                }else{
                    var message = data.roadmap_liked === 1 ? feedbackMessage.liked
                        : feedbackMessage.disliked;
                    var messageClass = {
                        add: data.roadmap_liked === 1 ? 'text-success': 'text-danger',
                        remove: data.roadmap_liked === 1 ? 'text-danger': 'text-success'
                    };
                    $('#feedback-section').hide();
                    $('#feedback-text').text(message).removeClass(messageClass.remove).addClass(messageClass.add);
                    $('#feedback-message').show();
                }


                // Verificar se há search_text para mostrar a aba de fontes
                // IMPORTANTE: Sempre esconder primeiro, depois mostrar apenas se houver search_text
                var $tabSearchSources = $('#tab-search-sources');

                // Forçar escondimento usando CSS inline para garantir
                $tabSearchSources.css('display', 'none');
                $tabSearchSources.attr('style', 'display: none !important');
                $('#search-sources-content').html('');

                if(data.search_text && data.search_text.trim() !== '') {
                    console.log('[Roadmaps] Exibindo aba de fontes - search_text encontrado:', data.search_text.substring(0, 50));
                    // Mostrar a aba de fontes
                    $tabSearchSources.css('display', '');
                    $tabSearchSources.attr('style', 'display: block');
                    $tabSearchSources.show();

                    // Formatar e exibir o search_text de forma amigável
                    let searchTextFormatted = data.search_text
                        // Converter markdown headers para HTML
                        .replace(/^=== (.+?) ===$/gm, '<h3 class="mt-4 mb-3">$1</h3>')
                        .replace(/^--- (.+?) ---$/gm, '<h4 class="mt-3 mb-2">$1</h4>')
                        // Converter links markdown para HTML
                        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-primary">$1</a>')
                        // Converter negrito markdown
                        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                        // Converter listas com bullet points
                        .replace(/^• (.+)$/gm, '<li class="mb-2">$1</li>')
                        // Converter quebras de linha
                        .replace(/\n/g, '<br>')
                        // Converter múltiplas quebras de linha em parágrafos
                        .replace(/(<br>\s*){3,}/g, '</p><p class="mb-3">')
                        // Adicionar parágrafo inicial
                        .replace(/^/, '<p class="mb-3">')
                        // Fechar parágrafo final
                        .replace(/$/, '</p>');

                    // Envolver em container para melhor apresentação
                    searchTextFormatted = '<div class="search-sources-formatted">' + searchTextFormatted + '</div>';

                    $('#search-sources-content').html(searchTextFormatted);
                } else {
                    console.log('[Roadmaps] Escondendo aba de fontes - sem search_text. search_text:', data.search_text);
                    // Garantir que está escondida - usar múltiplas abordagens
                    $tabSearchSources.css('display', 'none');
                    $tabSearchSources.attr('style', 'display: none !important');
                    $tabSearchSources.hide();
                    $('#search-sources-content').html('');

                    // Verificar se realmente está escondida
                    setTimeout(function() {
                        if($tabSearchSources.is(':visible')) {
                            console.warn('[Roadmaps] AVISO: Aba ainda está visível após esconder! Forçando escondimento novamente.');
                            $tabSearchSources.css('display', 'none !important');
                            $tabSearchSources.hide();
                        }
                    }, 100);
                }
            }
        }
    });

    $('.jwc_contact_modal_headlines_geradas').fadeIn(200);

    return false;
});

 // Feedback dos roteiros
$("#roadmap-feedback-btn-liked, #roadmap-feedback-btn-disliked").on("click", function(){
    var feedback = $(this).data("feedback");
    var roadmap_id = $(this).attr('roadmap_id');
    var message = feedback == 1 ? feedbackMessage.liked
        : feedbackMessage.disliked;

    $('#feedback-section').hide();
    $('#feedback-text').removeClass('text-success text-danger').text(message).addClass(feedback === 1 ? 'text-success': 'text-danger');;
    $('#feedback-message').show();

    if(feedback != 1){
        $('#feedback-message').hide();
        $("#textarea_reason").fadeIn();
    }


    let feedbackValue = parseInt(feedback, 10);

    $.ajax({
        url: "dashboard/user/roadmaps/setFeedback",
        type: "POST",
        dataType: 'json',
        data: {
            roadmap_id: roadmap_id,
            feedback: feedbackValue,
        },
        success: ((response) => {
            toastr.success(response.message);
        }),
        error: ((xrt) => {
            console.log(xrt.responseText)
        })
    });
});

$("#send-reason-unliked").on("click", function(){
    $("#textarea_reason").hide();
    $('#feedback-message').show();
    var roadmap_id = $('#roadmap-feedback-btn-disliked').attr('roadmap_id');
    $.ajax({
        url: "dashboard/user/roadmaps/set/reason",
        type: "POST",
        dataType: 'json',
        data: {
            roadmap_id: roadmap_id,
            reason_unliked: $("#reason_unliked").val() ?? '',
        },
        success: ((response) => {
            toastr.success(response.message);
        }),
        error: ((xrt) => {
            console.log(xrt.responseText)
        })
    });
});

$('#modal-customer-roadmap-edit-roadmap').on('hidden.bs.modal', function (e) {
    // Esconder a aba de fontes ao fechar o modal - usar CSS inline para garantir
    var $tabSearchSources = $('#tab-search-sources');
    $tabSearchSources.css('display', 'none');
    $tabSearchSources.attr('style', 'display: none !important');
    $tabSearchSources.hide();
    $('#search-sources-content').html('');
    $("#reason_unliked").val('');
    $("#textarea_reason").hide();
    // Limpar e esconder a aba de fontes de pesquisa
    $('#tab-search-sources').hide();
    $('#search-sources-content').html('');
    var $editForm = $('form#form-customer-roadmaps-edit');
    $editForm.removeData('chat-resource-id');
});

$('form#form-customer-roadmaps-edit').submit(function (e) {
    "use strict";
    e.preventDefault();

    // Atualiza o input hidden com o conteúdo mais recente do editor
    var quillContent = quill.root.innerHTML;
    document.getElementById('roadmap_gpt').value = quillContent;

    // Verifica se o conteúdo está vazio
    var cleanContent = quillContent.replace(/<[^>]*>/g, '').trim();
    if (!cleanContent || cleanContent === '') {
        toastr.error('O conteúdo do roteiro não pode estar vazio. Por favor, adicione algum conteúdo antes de salvar.');
        return false;
    }

    $('#update_customer_roadmap_button').prop('disabled', true);
    $('#update_customer_roadmap_button').text('Aguarde atualizando...');

    var formData = new FormData(this);

    // Adiciona o conteúdo do editor ao FormData
    formData.set('roadmap_gpt', quillContent);

    $.ajax({
        type: "post",
        url: 'dashboard/user/roadmaps/update',
        data: formData,
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#update_customer_roadmap_button').prop('disabled', false);
                $('#update_customer_roadmap_button').html('[SVG]\n'+
                    '                            Atualizar');
            }
            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.reset){
                $('#customer-headlines-edit')[0].reset();
                $('#customer-headlines-select-structures')[0].tomselect.clear();
            }
            if(data.modalOut){
                $('#modal-customer-headline-edit-headline').modal('hide');
            }

        },
        error: function(data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao salvar a pesquisa.');
            }

            $('#update_customer_roadmap_button').prop('disabled', false);
            $('#update_customer_roadmap_button').html('[SVG]\n'+
                '                            Atualizar');
        }
    });
    return false;
});

$('#start_roadmap_chat_button').on('click', function(e){
    e.preventDefault();
    var $button = $(this);
    var $form = $('form#form-customer-roadmaps-edit');
    var resourceId = $form.data('chat-resource-id');
    var resourceType = $form.data('chat-resource-type') || 'user_roadmaps';

    if (typeof window.startChatMode === 'function') {
        window.startChatMode(resourceId, resourceType, this);
        return;
    }

    if (!resourceId || !resourceType) {
        toastr.error('Roteiro não encontrado para iniciar o modo chat.');
        return;
    }

    $button.prop('disabled', true);

    var csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;

    var requestData = {
        resource_id: resourceId,
        resource_type: resourceType
    };

    if (csrfToken) {
        requestData._token = csrfToken;
    }

    $.ajax({
        url: '/dashboard/user/chat/start',
        method: 'POST',
        data: requestData,
        success: function(response) {
            if (response.success && response.redirect) {
                window.location.href = response.redirect;
            } else {
                toastr.error(response.message || 'Não foi possível iniciar o modo chat.');
            }
        },
        error: function(xhr) {
            var message = 'Não foi possível iniciar o modo chat.';
            if (xhr.responseJSON && xhr.responseJSON.message) {
                message = xhr.responseJSON.message;
            }
            toastr.error(message);
        },
        complete: function() {
            $button.prop('disabled', false);
        }
    });
});

if (typeof window.startChatMode !== 'function') {
    window.startChatMode = function (resourceId, resourceType, buttonElement) {
        if (!resourceId || !resourceType) {
            toastr.error('Roteiro não encontrado para iniciar o modo chat.');
            return;
        }

        var $button = $(buttonElement);
        $button.prop('disabled', true);

        var csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        var csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : null;

        var requestData = {
            resource_id: resourceId,
            resource_type: resourceType
        };

        if (csrfToken) {
            requestData._token = csrfToken;
        }

        $.ajax({
            url: '/dashboard/user/chat/start',
            method: 'POST',
            data: requestData,
            success: function(response) {
                if (response.success && response.redirect) {
                    window.location.href = response.redirect;
                } else {
                    toastr.error(response.message || 'Não foi possível iniciar o modo chat.');
                }
            },
            error: function(xhr) {
                var message = 'Não foi possível iniciar o modo chat.';
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

$('form#form-roadmap-reprocess').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#reprocess_roadmap_button').prop('disabled', true);
    $('#reprocess_roadmap_button').text('Aguarde reprocessando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: 'dashboard/user/roadmaps/reprocess',
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#update_customer_roadmap_button').prop('disabled', false);
                $('#update_customer_roadmap_button').html('[SVG]\n'+
                    '                            Atualizar');
            }
            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.reset){
                $('#customer-headlines-edit')[0].reset();
                $('#customer-headlines-select-structures')[0].tomselect.clear();
            }
            if(data.modalOut){
                $('#modal-customer-headline-edit-headline').modal('hide');
            }

        },
        error: function(data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao reprocessar o roteiro.');
            }

            $('#reprocess_roadmap_button').prop('disabled', false);
            $('#reprocess_roadmap_button').html('[SVG]\n'+
                '                            Gerar Roteiro');
        }
    });
    return false;
});

$('body').on('click', '.j_reprocess_roadmap', function (e) {
    e.preventDefault();
    var data = window.currentRoadmapViewData;
    if (!data) {
        toastr.warning('Abra o roteiro antes de reprocessar.');
        return;
    }
    var editModal = document.getElementById('modal-customer-roadmap-edit-roadmap');
    if (editModal) {
        var modalInstance = bootstrap.Modal.getInstance(editModal);
        if (modalInstance) modalInstance.hide();
    }
    if (window.AdvancedRoadmapModal && typeof window.AdvancedRoadmapModal.openForReprocess === 'function') {
        window.AdvancedRoadmapModal.openForReprocess(data);
    }
});

$('body').on('click', '.j_roadmaps_delete', function(){
    $('#modal-roadmaps-delete').modal('show');
    let id = $(this).attr('data-roadmap-id');
    $('.j_roadmaps_delete_confirm').attr('href', '/dashboard/user/roadmaps/delete/'+id);
})

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('select-core-brains');
    if (el) {
        new TomSelect(el, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            render:{
                item: function(data, escape) {
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }
});


document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('favorites-select-core-beliefs');
    if (el) {
        new TomSelect(el, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            render:{
                item: function(data, escape) {
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }
});

$('#customer-headlines-select-agents').change(function (e) {
    $('.question_roadmap').hide();
    $.ajax({
        url: "dashboard/user/roadmaps/get-question-roadmap",
        type: "POST",
        dataType: 'json',
        data: {
            agent_id: $(this).val()
        },
        success: function(data){
            if(data.questionRoadmap && data.questionRoadmap.length > 0){
                $('.question_roadmap').show();
                $('.title_question_roadmap').show();

                // Limpar container de questões existente
                $('#questions-container').empty();

                // Fazer foreach nas questões retornadas
                data.questionRoadmap.forEach(function(question, index) {
                    const questionHtml = `
                        <div class="question-item mb-3">
                            <div class="question-content">
                                <div class="question-number">${index + 1} - ${question.question}</div>
                                <input type="hidden" name="question_id[]" value="${index + 1} - ${question.question}">
                                <div class="question-text">
                                    <input type="text" class="form-control w-100" name="questions[]" required placeholder="Digite sua pergunta aqui..." required>
                                </div>
                            </div>
                        </div>
                    `;

                    $('#questions-container').append(questionHtml);
                });

                console.log(`Carregadas ${data.questionRoadmap.length} questões do agente`);

            } else {
                $('.question_roadmap').hide();
                $('#questions-container').empty();
                $('.title_question_roadmap').hide();
            }
        },
        error: function(data){
            $('.question_roadmap').hide();
            $('#questions-container').empty();
            console.error('Erro ao carregar questões:', data);
        }
    });
});
$('.title_question_roadmap').hide();


$(document).ready(function() {

    $('body').on('click', '.js_view_headline_from_id', function(){
        const source = $(this).data('source');
        const sourceID = $(this).data('source-id');
        let newLocation = null;
        if(source){
            switch(source){
                case 'suggested':
                    newLocation = '/dashboard/user/headlines/suggested?hid='+sourceID;
                    break;
                case 'favorite':
                    newLocation = '/dashboard/user/headlines/favorites?hid='+sourceID;
                    break
            }
        }
        if(!newLocation) {
            console.error('Nenhuma localização encontrada');
            return;
        }

        const url = new URL(window.location.href);
        let newUrl = `${url.origin}${newLocation}`;
        if (location.hostname != "localhost") {
            if (newUrl.startsWith('http://')) {
                newUrl = newUrl.replace('http://', 'https://');
            }
        }
        window.location.href = newUrl;
    })


});

