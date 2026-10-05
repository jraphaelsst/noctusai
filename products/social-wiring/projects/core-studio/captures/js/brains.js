var audioPendente = 0;

$(document).ready(function () {

    $('form#brains').submit(async function (e) {
    "use strict";
    e.preventDefault();

    $('#brain_button_save').prop('disabled', true);
    $('#brain_button_save').addClass('hidden');
    $('#brain_button_save').text('Aguarde atualizando...');

    var formData = new FormData(this);

    formData.append('typeSubmit', 'aplica_todos');

    $("#brain_button_save").prop("disabled", true).text("Aguarde, processando respostas!");     

    // for (var questionId in recordings) {
    //     if (recordings.hasOwnProperty(questionId)) {
    //         if (recordings[questionId].audioBlob) {
    //             // Ex: audio[3] será o nome do campo para a pergunta de id 3
    //             formData.append('audio[' + questionId + ']', recordings[questionId].audioBlob, 'recording_' + questionId + '.mp3');
    //         }
    //     }
    // }

    let uploadedAudios = {}; // Armazena os nomes dos arquivos de áudio processados

    for (var questionId in recordings) {
        if (recordings.hasOwnProperty(questionId)) {
            if (recordings[questionId].audioBlob) {
                let audioBlob = recordings[questionId].audioBlob;

                try {
                    // Envia o áudio em chunks e recebe o nome do arquivo processado
                    let uploadedFileName = await sendAudioChunks(audioBlob, questionId);
                    uploadedAudios[questionId] = uploadedFileName;
                    if (audioPendente > 0) {
                        audioPendente -= 1;
                    }
                } catch (error) {
                    alert("Erro ao enviar o áudio. Tente novamente.");
                    console.error("Erro no envio dos chunks:", error);
                    $('#brain_button_save').prop('disabled', false);
                    $('#brain_button_save').html('Aplicar Alterações');
                    return; // Interrompe a execução se houver erro no upload do áudio
                }
            }
        }
    }

    // Adiciona os nomes dos arquivos de áudio ao formData
    for (var questionId in uploadedAudios) {
        formData.append('audio[' + questionId + ']', uploadedAudios[questionId]);
    }


    $.ajax({
        type: "post",
        url: "/dashboard/user/cores/update",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            audioPendente = 0;
            toastr[data.type](data.message);

            if(data.button){
                $('#brain_button_save').prop('disabled', false);
                $('#brain_button_save').html('Aplicar Alterações');
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
                $('#agent-create')[0].reset();
                $('.j_option_text').fadeOut();
                $('.j_option_url').fadeIn();
                $('#modal-new-agent').modal('hide');
            }

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao atualizar o cérebro.');
                }
            } 

            $('#brain_button_save').prop('disabled', false);
            $('#brain_button_save').html('Aplicar Alterações'); 
        }
    });
    return false;
});

$('form#make_core').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#button_add_core').prop('disabled', true);
    $('#button_add_core').text('Aguarde criando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/cores/custom/add",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#button_add_core').prop('disabled', false);
                $('#button_add_core').html('Atualizar');
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
                $('#agent-create')[0].reset();
                $('.j_option_text').fadeOut();
                $('.j_option_url').fadeIn();
                $('#modal-new-agent').modal('hide');
            }

        },
        error: function(data) {

            if(data.status == 422){
                const errors = data?.responseJSON?.errors?.name;
                const errorMessage = Array.isArray(errors) && errors[0] ? errors[0] : 'Ocorreu um erro ao criar o núcleo.';
                toastr.error(errorMessage);
                $('#button_add_core').prop('disabled', false);
                $('#button_add_core').html('criar');
                return false;
            }
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao criar o núcleo.');
                }
            }

            $('#button_add_core').prop('disabled', false);
            $('#button_add_core').html('criar');
        }
    });
    return false;
});

$('form#edit_core').submit(async function (e) {
    "use strict";
    e.preventDefault();

    $('#button_update_core').prop('disabled', true);
    $('#button_update_core').text('Aguarde atualizando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/cores/custom/update",
        data: formData,
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#button_update_core').prop('disabled', false);
                $('#button_update_core').html('Atualizar');
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
                $('#edit_core')[0].reset();
                $('#modal-edit-core').modal('hide');
            }

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao atualizar o núcleo.');
                }
            }

            $('#button_update_core').prop('disabled', false);
            $('#button_update_core').html('Atualizar');
        }
    });
    return false;
}); 
// $(document).on('click', '.question_details', function () {
//     let htmlButton = $(this).html();
//     if(htmlButton == "Exibir perguntas detalhadas"){
//         $(this).html("Exibir resposta final");
//         $(".all_questions").removeClass("hidden");
//         $(".response_brain").addClass("hidden");
//     }else if(htmlButton == "Exibir resposta final"){
//         $(this).html("Exibir perguntas detalhadas");
//         $(".all_questions").addClass("hidden");
//         $(".response_brain").removeClass("hidden");
//     }
// });

$(document).on('click', '.j_core_edit', function () {
    $('form#edit_core input[name=core_id]').val('');
    $('form#edit_core input[name=name]').val('');

    var id = $(this).data('core-id');
    var name = $(this).data('core-name');

    $('form#edit_core input[name=core_id]').val(id);
    
    $('form#edit_core input[name=name]').val(name || '');

    $('#modal-edit-core').modal('show')

    return false;
});

$('body').on('click', '.j_core_delete', function(){
    $('#modal-core-delete').modal('show');
    let id = $(this).attr('data-core-id');
    $('.j_core_delete_confirm').attr('href', '/dashboard/user/cores/custom/delete/'+id);
})

// $(document).on('click', '.j_core_delete', function () {
//     var id = $(this).data('core-id');

//     $('.j_button_delete_confirm').attr('href', '/dashboard/user/cores/custom/delete/' + id);

//     return false;
// });
// Insere os ícones SVG
$(".icon-microphone").html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler-microphone"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 2m0 3a3 3 0 0 1 3 -3h0a3 3 0 0 1 3 3v5a3 3 0 0 1 -3 3h0a3 3 0 0 1 -3 -3z" /><path d="M5 10a7 7 0 0 0 14 0" /><path d="M8 21l8 0" /><path d="M12 17l0 4" /></svg>');
$(".icon-pencil").html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler-pencil"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4" /><path d="M13.5 6.5l4 4" /></svg>');
$(".icon-pause").html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler-player-pause"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M6 5m0 1a1 1 0 0 1 1 -1h2a1 1 0 0 1 1 1v12a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1z" /><path d="M14 5m0 1a1 1 0 0 1 1 -1h2a1 1 0 0 1 1 1v12a1 1 0 0 1 -1 1h-2a1 1 0 0 1 -1 -1z" /></svg>');
$(".icon-trash").html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler-trash"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0" /><path d="M10 11l0 6" /><path d="M14 11l0 6" /><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" /><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" /></svg>');


// Alterna entre falar e escrever
$(".option-speek").click(function(){
    let id = $(this).data('id');
    let textElement = $("#text-speek\\[" + id + "\\]");
    let txtArea = $("#txt-area\\[" + id + "\\]");
    let audioArea = $("#audio-area\\[" + id + "\\]");
    let icons = $(`.icons-speek[data-id="${id}"]`);
    let micIcon = icons.find(".icon-microphone");
    let pencilIcon = icons.find(".icon-pencil");
    let container = $("#info-area\\[" + id + "\\]");

    if (textElement.text().trim() === "Prefiro falar") {
        textElement.text("Prefiro escrever");
        txtArea.addClass("hidden");  
        audioArea.removeClass("hidden");
        micIcon.addClass("hidden");
        pencilIcon.removeClass("hidden");
    } else {
        textElement.text("Prefiro falar");
        txtArea.removeClass("hidden");  
        audioArea.addClass("hidden");
        micIcon.removeClass("hidden");
        pencilIcon.addClass("hidden");
    }
});


// Objeto para armazenar o estado de cada gravação (por pergunta)
let recordings = {};

    // Função para configurar o canvas
    function setupCanvas(canvas) {
        const scale = window.devicePixelRatio || 1;
        canvas.width = canvas.offsetWidth * scale;
        canvas.height = canvas.offsetHeight * scale;
        canvas.getContext("2d").scale(scale, scale);
    }

    //

    $("textarea.form-area").each(function () {
        $(this).data("original-value", $(this).val()); // Salva o valor original do textarea
    });
    
    $("textarea.form-area").on("input", function () {
        let questionId = $(this).attr("id").match(/\[(\d+)\]/)[1]; // Extrai o número do ID
        let container = $("#info-area\\[" + questionId + "\\]"); // Seleciona o container correto
        let inputPermission = $("input[name='permission\\[" + questionId + "\\]']");
        let waitingStatus = container.find(".waitingStatus");
        let audioControls = container.find("#audio-controls\\[" + questionId + "\\]"); // Div de controle do áudio
        let audioPlayer = container.find("#audio-player\\[" + questionId + "\\]"); // Player de áudio
        let divAudio = container.find(".div-audio"); // Área de gravação
        let divControls = container.find(".div-controls"); // Controles pós-gravação
        let recordTimer = container.find("#record-timer\\[" + questionId + "\\]");
    
        let statusLine = waitingStatus.find(".statusLine"); // Texto do status
        let statusText = waitingStatus.find(".ps-2"); // Texto do status
        let divAplicarAlteracoes = waitingStatus.find(".divAplicarAlteracoes"); // Botão "Aplicar alteração"

        let originalValue = $(this).data("original-value"); // Obtém o valor original
        let currentValue = $(this).val().trim(); // Obtém o valor atual do textarea
    
        if (currentValue !== originalValue) {
            inputPermission.val(1); // Se diferente do original, altera para 1

            waitingStatus.removeClass("hidden"); // Exibe a .waitingStatus
            statusLine.removeClass("success process");
            statusLine.addClass("waiting");
            divAplicarAlteracoes.removeClass("hidden");
            statusText.html("Alterações não aplicadas");

            if (recordings[questionId] && recordings[questionId].audioBlob) {
                console.log("Excluindo gravação do questionId:", questionId);
                delete recordings[questionId].audioBlob; // Remove o arquivo do objeto
                audioPlayer.attr("src", ""); // Remove o áudio do player
                divControls.addClass("hidden"); // Esconde os controles pós-gravação
                divAudio.removeClass("hidden"); // Exibe a área de gravação novamente
                recordTimer.text("00:00");

            }
        } else {
            inputPermission.val(0); // Se voltar ao original, redefine para 0
            waitingStatus.addClass("hidden"); // Esconde a .waitingStatus
        }
    });
    
    

   // Inicia ou para a gravação ao clicar no botão de gravar
   $(".record-button").click(async function () {
    let questionId = $(this).data("id");
    let container = $("#info-area\\[" + questionId + "\\]");

    // Se não existir estado para essa pergunta, cria-o
    if (!recordings[questionId]) {
        recordings[questionId] = {
            isRecording: false,
            timer: null,
            seconds: 0,
            mediaRecorder: null,
            audioChunks: [],
            audioContext: null,
            analyser: null,
            dataArray: null,
            audioBlob: null, // Armazenda o áudio, sem enviar 

        };
    }
    let rec = recordings[questionId];

    // Seleciona os elementos relacionados
    let recButton = container.find("#record-button\\[" + questionId + "\\]");
    let micIcon = recButton.find(".mic-icon");
    let micPause = recButton.find(".mic-pause");
    let recIndicator = container.find("#recording-indicator\\[" + questionId + "\\]");
    let recordTimer = container.find("#record-timer\\[" + questionId + "\\]");
    let audioControls = container.find("#audio-controls\\[" + questionId + "\\]");
    let audioPlayer = container.find("#audio-player\\[" + questionId + "\\]");
    let divAudio = container.find(".div-audio");
    let divControls = container.find(".div-controls");
    let canvas = container.find("canvas")[0];
    let waitingStatus = container.find(".waitingStatus");
    let inputPermission = $("input[name='permission\\[" + questionId + "\\]']");
    let formArea = container.find("#form-area\\[" + questionId + "\\]");   

    let statusLine = waitingStatus.find(".statusLine"); // Texto do status
    let statusText = waitingStatus.find(".ps-2"); // Texto do status
    let divAplicarAlteracoes = waitingStatus.find(".divAplicarAlteracoes"); // Botão "Aplicar alteração"

    setupCanvas(canvas);

    const mimeType = MediaRecorder.isTypeSupported('audio/webm') 
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4') 
            ? 'audio/mp4'
            : MediaRecorder.isTypeSupported('audio/mp3') 
                ? 'audio/mp3'
                : null; 

    if (!mimeType) {
        console.error("Nenhum formato de áudio suportado pelo navegador para gravação.");
        rec.isRecording = false; 
        toastr['error']("Ops! Parece que seu navegador não tem suporte para esse recurso, tente outro!");
        return; 
    }

    if (!rec.isRecording) {
        try {
            // Inicia gravação
            rec.isRecording = true;
            micIcon.addClass("hidden");
            micPause.removeClass("hidden");
            recIndicator.removeClass("hidden");

            waitingStatus.addClass("hidden");
            inputPermission.val(0);
            formArea.val('');
            // Reinicia timer
            rec.seconds = 0;
            recordTimer.text("00:00");
            rec.timer = setInterval(() => {
                rec.seconds++;
                recordTimer.text(new Date(rec.seconds * 1000).toISOString().substr(14, 5));
            }, 1000);

            // Solicita stream de áudio
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            rec.audioContext = new AudioContext();
            rec.analyser = rec.audioContext.createAnalyser();
            rec.analyser.fftSize = 256;
            rec.dataArray = new Uint8Array(rec.analyser.frequencyBinCount);
            let source = rec.audioContext.createMediaStreamSource(stream);
            source.connect(rec.analyser);

        // rec.mediaRecorder = new MediaRecorder(stream);
            rec.mediaRecorder = new MediaRecorder(stream, {
                mimeType: mimeType,
                audioBitsPerSecond: 128000 // Reduz a taxa de bits para 128kbps
            });
            rec.mediaRecorder.start();
            rec.audioChunks = [];
            rec.mediaRecorder.ondataavailable = event => {
                rec.audioChunks.push(event.data);
            };

            // Função para desenhar o waveform
            rec.drawWaveform = function () {
                if (!rec.isRecording) return;
                rec.analyser.getByteFrequencyData(rec.dataArray);
                let ctx = canvas.getContext("2d");
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const barCount = 164;
                const barWidth = Math.floor(canvas.width / barCount) - 2;
                let x = 0;
                for (let i = 0; i < barCount; i++) {
                    const index = Math.floor((i / barCount) * rec.dataArray.length);
                    const barHeight = (rec.dataArray[index] / 255) * canvas.height * 0.8;
                    ctx.fillStyle = "#0054A6";
                    ctx.fillRect(x, (canvas.height - barHeight) / 2, barWidth, barHeight);
                    x += barWidth + 2;
                }
                requestAnimationFrame(rec.drawWaveform);
            };
            rec.drawWaveform();
        } catch (error) {
            console.error("Erro ao iniciar gravação:", error);
            toastr['error']("Erro ao acessar o microfone. Verifique as permissões!");
            rec.isRecording = false;
            clearInterval(rec.timer);
            return;
        }
    } else {
        // Para a gravação
        audioPendente += 1;
        rec.isRecording = false;
        micIcon.removeClass("hidden");
        micPause.addClass("hidden");
        recIndicator.addClass("hidden");
        waitingStatus.removeClass("hidden");

        statusLine.removeClass("success process");
        statusLine.addClass("waiting");
        divAplicarAlteracoes.removeClass("hidden");
        statusText.html("Alterações não aplicadas");


        inputPermission.val(1);
        
        clearInterval(rec.timer);
        let ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Ao parar, exibe os controles de áudio e oculta a área de gravação
        divAudio.addClass("hidden");
        divControls.removeClass("hidden");

        rec.mediaRecorder.stop();
        // rec.mediaRecorder.onstop = () => {
        //     const audioBlob = new Blob(rec.audioChunks, { type: "audio/mp3" });
        //     const audioUrl = URL.createObjectURL(audioBlob);
        //     audioPlayer.attr("src", audioUrl);
        // };
        rec.mediaRecorder.onstop = () => {
            const audioBlob = new Blob(rec.audioChunks, { type: mimeType });
            // Armazena o blob para envio
            rec.audioBlob = audioBlob;
            const audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.attr("src", audioUrl);
        };
        
    }
});
    // Handler para o botão de excluir (trash)
    $("[id^='delete-button']").click(function () {

        if (audioPendente > 0) {
            audioPendente -= 1;
        }
        // Extrai o id da pergunta a partir do id (ex.: "delete-button[3]")
        let id = $(this).attr("id").match(/\[(\d+)\]/)[1];
        let container = $("#info-area\\[" + id + "\\]");
        let recordTimer = container.find("#record-timer\\[" + id + "\\]");
        let divAudio = container.find(".div-audio");
        let divControls = container.find(".div-controls");
        let recButton = container.find("#record-button\\[" + id + "\\]");
        let micIcon = recButton.find(".mic-icon");
        let micPause = recButton.find(".mic-pause");
        let recIndicator = container.find("#recording-indicator\\[" + id + "\\]");
        let audioControls = container.find("#audio-controls\\[" + id + "\\]");
        let audioPlayer = container.find("#audio-player\\[" + id + "\\]");
        let canvas = container.find("canvas")[0];
        let waitingStatus = container.find(".waitingStatus");
        let inputPermission = $("input[name='permission\\[" + id + "\\]']"); // ESCAPANDO OS []

        // Restaura os elementos: oculta os controles, mostra a área de gravação
        recordTimer.text("00:00");
        divControls.addClass("hidden");
        divAudio.removeClass("hidden");

        waitingStatus.addClass("hidden");
        inputPermission.val(0);

        micIcon.removeClass("hidden");
        micPause.addClass("hidden");
        recIndicator.addClass("hidden");
        audioPlayer.attr("src", "");
        if (canvas) {
            let ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        // Se houver um estado de gravação para esta pergunta, reseta-o
        if (recordings[id]) {
            clearInterval(recordings[id].timer);
            recordings[id].isRecording = false;
            recordings[id].audioChunks = [];
        }
    });

    // Se necessário, reconfigura os canvases ao redimensionar a tela
    window.addEventListener("resize", function () {
        $("[id^='waveform']").each(function () {
            setupCanvas(this);
        });
    });

    $(".aplicarAlteracoes").click(async function () {
        let questionId = $(this).attr("id").match(/\[(\d+)\]/)[1]; // Obtém o ID da pergunta
        let container = $("#info-area\\[" + questionId + "\\]");
        let waitingStatus = container.find(".waitingStatus"); // Status da pergunta

        let applyButton = waitingStatus.find(".aplicarAlteracoes"); // Botão "Aplicar alteração"

        applyButton.prop('disabled', true);
        applyButton.text("Aguarde o upload do audio..."); 
    });
    $(".aplicarAlteracoes").click(async function () {
        let questionId = $(this).attr("id").match(/\[(\d+)\]/)[1]; // Obtém o ID da pergunta
        let container = $("#info-area\\[" + questionId + "\\]");
        let audioPlayer = container.find("#audio-player\\[" + questionId + "\\]");
        let formArea = container.find("#form-area\\[" + questionId + "\\]");  
        let inputPermission = $("input[name='permission\\[" + questionId + "\\]']");
        let coreId = $("input[name='core_id']").val(); // Obtém o core_id da pergunta
        let waitingStatus = container.find(".waitingStatus"); // Status da pergunta
        let statusLine = waitingStatus.find(".statusLine"); // Texto do status
        let statusText = waitingStatus.find(".ps-2"); // Texto do status
        let applyButton = waitingStatus.find(".aplicarAlteracoes"); // Botão "Aplicar alteração"
        let txtArea = $("#txt-area\\[" + questionId + "\\]");
        let audioArea = $("#audio-area\\[" + questionId + "\\]");

        applyButton.prop('disabled', true);
        applyButton.text("Aguarde o upload do audio..."); 
        $("#brain_button_save").prop("disabled", true);            

        let formData = new FormData();
        let audioSent = false; // Flag para verificar se o áudio foi enviado

        formData.append("core_id", coreId);
        formData.append("question_id", questionId);
    
        if (inputPermission.val() == "1") {
            // O usuário escreveu no textarea → Enviar texto
            formData.append(`response[${questionId}]`, formArea.val().trim());
    
            // O usuário gravou um áudio → Verificar se a gravação existe antes de enviar
            if (recordings[questionId] && recordings[questionId].audioBlob) {
                let audioBlob = recordings[questionId].audioBlob;
                
                // **Enviar o áudio em chunks primeiro**
                try {
                    // **Aguarda o upload e recebe o nome do arquivo**
                    let uploadedFileName = await sendAudioChunks(audioBlob, questionId);
                    formData.append(`audio[${questionId}]`, uploadedFileName); // Envia o nome do arquivo
    
                } catch (error) {
                    alert("Erro ao enviar o áudio. Tente novamente.");
                    console.error("Erro no envio dos chunks:", error);
                    return; // Interrompe o envio se o áudio falhar
                }
            } 
        } else {
            alert("Nenhuma informação encontrada para enviar.");
            return;
        }
        
        $.ajax({
            url: "/dashboard/user/cores/update", 
            type: "POST",
            data: formData,
            processData: false,
            contentType: false,
            success: function (response) {
                statusLine.removeClass("waiting").addClass("proccess");
                statusText.text("Aguarde, processando resposta!");
                applyButton.remove();
                txtArea.addClass("hidden");  
                audioArea.addClass("hidden");
                $("#brain_button_save").prop("disabled", true);            
            },
            error: function (xhr, status, error) {
                alert("Erro ao enviar. Tente novamente.");
                console.error(xhr.responseText);
                $("#brain_button_save").prop("disabled", false);            
            }
        });
    });
    
    const sendAudioChunks = async (audioBlob, questionId) => {
        return new Promise(async (resolve, reject) => {
            const CHUNK_SIZE = 1024 * 1024; // Reduzido para 512 KB (metade de 1 MB)
            const totalChunks = Math.ceil(audioBlob.size / CHUNK_SIZE);
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
            let finalFileName = null;
    
            try {
                for (let i = 0; i < totalChunks; i++) {
                    const start = i * CHUNK_SIZE;
                    const end = Math.min(start + CHUNK_SIZE, audioBlob.size);
                    const chunk = audioBlob.slice(start, end);
    
                    const formData = new FormData();
                    formData.append('audio_chunk', chunk, `chunk_${i}.webm`);
                    formData.append('chunk_number', i);
                    formData.append('total_chunks', totalChunks);
                    formData.append('question_id', questionId);
    
                    console.log(`Enviando chunk ${i + 1} de ${totalChunks}, tamanho: ${chunk.size} bytes`);
    
                    const response = await fetch('/dashboard/user/cores/upload-audio-chunk', {
                        method: 'POST',
                        headers: {
                            'X-CSRF-TOKEN': csrfToken
                        },
                        body: formData
                    });
    
                    if (!response.ok) {
                        throw new Error(`Erro HTTP: ${response.status} - ${response.statusText}`);
                    }
    
                    const result = await response.json();
                    console.log(result);
    
                    if (result.success && result.file) {
                        finalFileName = result.file;
                    }
                }
    
                if (finalFileName) {
                    console.log(`Arquivo final salvo: ${finalFileName}`);
                    resolve(finalFileName);
                } else {
                    reject("Erro ao obter nome do arquivo final");
                }
            } catch (error) {
                console.error("Erro ao enviar chunks:", error);
                reject(error);
            }
        });
    };  
    
    function showModal(event) {
        console.log("audioPendente:", audioPendente);

        if (audioPendente > 0) {
            if (event) event.preventDefault(); // Bloqueia F5, voltar, etc., apenas se houver upload pendente
            $('#modal-reload').modal('show');
        } else {
            if (event && event.type === "keydown") {
                location.reload(); // Se for um evento de F5, executa o reload normalmente
            } else if (event && event.type === "popstate") {
                history.back(); // Se for um evento de voltar, permite a ação
            }
        }
    }

    // Detecta quando o mouse sai da janela do navegador (pela parte superior)
    $(document).mouseleave(function (event) {
        if (event.clientY <= 0) {
            showModal();
        }
    });

    // Bloqueia F5, Ctrl+R e Command+R (Mac) apenas se houver upload pendente
    $(document).keydown(function (event) {
        if (event.keyCode === 116 ||  // F5
            (event.ctrlKey && event.keyCode === 82) || // Ctrl+R (Windows/Linux)
            (event.metaKey && event.keyCode === 82)) { // Command+R (Mac)
            showModal(event);
        }
    });

    // Bloqueia o botão Voltar do navegador apenas se houver upload pendente
    $(document).ready(function () {
        history.pushState(null, null, location.href);
        window.onpopstate = function (event) {
            showModal(event);
        };
    });

    // Exibe aviso antes de sair da página apenas se houver upload pendente
    window.onbeforeunload = function () {
        if (audioPendente > 0) {
            return "Você tem uploads em andamento. Tem certeza de que deseja sair?";
        }
    };

    // Quando um áudio começa a ser gravado, incrementa `audioPendente`
    $(".record-button").click(function () {
        audioPendente += 1;
    });

    // Quando o áudio é excluído, decrementa `audioPendente`
    $("[id^='delete-button']").click(function () {
        if (audioPendente > 0) {
            audioPendente -= 1;
        }
    });

    // Dropzone: highlight drag-over e preview do nome do arquivo
    var $dropzone = $('#upload-dropzone');
    var $fileInput = $('#file');

    $dropzone.on('dragover dragenter', function (e) {
        e.preventDefault();
        $(this).css('border-color', 'var(--tblr-primary)');
    }).on('dragleave drop', function (e) {
        e.preventDefault();
        $(this).css('border-color', '');
        if (e.type === 'drop') {
            var dt = e.originalEvent.dataTransfer;
            if (dt && dt.files.length) {
                $fileInput[0].files = dt.files;
                $fileInput.trigger('change');
            }
        }
    });

    $fileInput.on('change', function () {
        var f = this.files[0];
        if (f) {
            $('#upload-label-text').html('<strong>' + f.name + '</strong>');
            $dropzone.css('border-color', 'var(--tblr-primary)');
        } else {
            $('#upload-label-text').text('Clique para escolher ou arraste o arquivo aqui');
            $dropzone.css('border-color', '');
        }
    });

    // Resetar dropzone ao fechar modal
    $('#modal-upload-core').on('hidden.bs.modal', function () {
        $fileInput.val('');
        $('#upload-label-text').text('Clique para escolher ou arraste o arquivo aqui');
        $dropzone.css('border-color', '');
        $('#button_upload_core').prop('disabled', false).text('Enviar arquivo');
    });

    $("#button_upload_core").click(function (e) {
        e.preventDefault();
        var $btn = $(this);
        var coreId = $("#core_upload_id").val();
        var fileInput = $("#file")[0];
        var file = fileInput.files[0];

        if (!file) {
            toastr.error('Selecione um arquivo antes de enviar.');
            return;
        }

        var allowedExt = ['pdf', 'docx', 'txt', 'md', 'csv'];
        var ext = file.name.split('.').pop().toLowerCase();
        if (!allowedExt.includes(ext)) {
            toastr.error('Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.');
            return;
        }

        if (file.size > 20 * 1024 * 1024) {
            toastr.error('Arquivo muito grande. Limite: 20 MB.');
            return;
        }

        var formData = new FormData();
        formData.append("core_id", coreId);
        formData.append("file", file);
        formData.append("_token", $('meta[name="csrf-token"]').attr('content'));

        $btn.prop('disabled', true).html(
            '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Processando…'
        );

        $.ajax({
            url: "/dashboard/user/cores/upload-file",
            type: "POST",
            data: formData,
            processData: false,
            contentType: false,
            success: function () {
                window.location.href = '/dashboard/user/cores';
            },
            error: function (xhr) {
                var msg = xhr.responseJSON && xhr.responseJSON.message
                    ? xhr.responseJSON.message
                    : 'Erro ao enviar arquivo. Tente novamente.';
                toastr.error(msg);
                $btn.prop('disabled', false).text('Enviar arquivo');
            }
        });
    });
 

    
});
