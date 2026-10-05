//Make Headlines Modal Select Clientes
//@formatter:off

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('make-headlines-select-agents');
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
    var el = document.getElementById('make-headlines-select-customers');
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
    var el = document.getElementById('make-headlines-select-structures');
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
    var el = document.getElementById('make-headlines-select-variables');
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

$(document).ready(function() {
    // Evento para capturar a mudança do select de clientes
    $('form#make-headlines select[name="client_id"]').on('change', function() {
        var clientId = $(this).val(); // Pega o ID do cliente selecionado

        if (clientId) {
            $.ajax({
                url: '/dashboard/make-headlines/get-structures/' + clientId,
                type: 'GET',
                dataType: 'json',
                success: function(data) {
                    var structureSelect = $('select[name="structure_id[]"]');
                    structureSelect.empty(); // Limpa o select

                    // Adiciona a opção padrão "Todas"
                    structureSelect.append('<option>Todas</option>');

                    // Adiciona as opções dinamicamente
                    $.each(data, function(key, value) {
                        structureSelect.append('<option value="'+ value.id +'">'+ value.name +'</option>');
                    });
                }
            });
        } else {
            $('select[name="structure_id[]"]').empty();
        }
    });
});

$('#make-headlines-select-customers').on('change', function(){
    let customer_id = $(this).closest('#make-headlines').find('#make-headlines-select-customers').val();

    $.ajax({
        type: 'post',
        url: 'dashboard/make-headlines/get-variables-type',
        data: {
            customer_id: customer_id
        },
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.content_option) {
                $("form#make-headlines select[name='variable_type_id']").html(data.content_option).trigger('change')
            }
        }
    });
}) 

$('#make-headlines-select-customers-variables-type').on('change', function(){
    let customer_id = $(this).closest('#make-headlines').find('#make-headlines-select-customers').val();
    let variable_type_id = $(this).val()

    $('#make-headlines-select-variables')[0].tomselect.clear();
    $('.j_all_values').fadeOut();

    $.ajax({
        type: 'post',
        url: 'dashboard/make-headlines/get-variables',
        data: {
            customer_id: customer_id,
            variable_type_id: variable_type_id
        },
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.content_option) {
                $("#make-headlines-select-variables").html(data.content_option)
            }
        }
    });
})

$('#make-headlines-select-variables').on('change', function(){
    let variables = $(this).val();
    let customer_id = $(this).closest('#make-headlines').find('#make-headlines-select-customers').val();
    let variable_type_id = $(this).closest('#make-headlines').find('#make-headlines-select-customers-variables-type').val();

    $.ajax({
        type: 'post',
        url: 'dashboard/make-headlines/get-variables-values',
        data: {
            //callback: 'Estrutura',
            //callback_action: 'get_variables',
            variables: variables,
            customer_id: customer_id,
            variable_type_id: variable_type_id
        },
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.content_option) {
                if($('form#make-headlines input[name=add_input]').val() == '1'){
                    $(".j_all_values").fadeIn();
                    $(".j_all_values").html(data.content_option)
                }
            }
        }
    });
})

$('#make-headlines-select-variables-user').on('change', function () {
    // Obtém a lista de valores selecionados
    const selectedValues = $(this).val() || [];
    
    // Verifica se "all" está entre os valores selecionados
    if (selectedValues.includes('all')) {
        $('.input_two').hide();
        $('.label_one').click();
    } else {
        // Mostra a div
        $('.input_two').show();
    }
});

$('#make-headlines-select-variables-user').on('change', function(){
    let customer_id = $(".user_id_input").val()
    let variables = $(this).val();

    $.ajax({
        type: 'post',
        url: 'dashboard/user/headlines/get-variables-values',
        data: {
            customer_id: customer_id,
            variables: variables
        },
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.content_option) {
                $(".j_all_values").html('');
                $(".j_all_values").html(data.content_option);
            }
        }
    });
})

$('form#make-headlines input[name=add_input]').on('change', function(){
    if($(this).val() == '2'){
        $('.j_make_headlines_input_user').fadeIn()
        $('.j_make_headlines_make_software').fadeOut()
    }else{
        $('.j_make_headlines_input_user').fadeOut()
        $('.j_make_headlines_make_software').fadeIn()
    }
})



$('.j_make_headlines_clear_fields').click(function(){
    console.log('clear')
    $('#make-headlines')[0].reset();
    $('#make-headlines-select-customers')[0].tomselect.clear();
    $('#make-headlines-select-structures')[0].tomselect.clear();
    $('#make-headlines-select-variables')[0].tomselect.clear();
    $('.j_all_values').fadeOut(300);
    $('.j_make_headlines_input_user').fadeOut(300);
})

//HEADLINE BOX

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('box-headlines-select-customers');
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

$('#box-headlines-select-customers').on('change', function(){
    let customer_id = $(this).val();

    $.ajax({
        type: 'get',
        url: 'dashboard/box-headlines/customer/'+customer_id+'/list',
        data: {
            customer_id: customer_id
        },
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if(data.message){
               toastr[data.type](data.message);
            }
            if (data.options) {
                $("form#form_box_headlines_save select[name='headline_week_id']").html(data.options)
                $('form#form_box_headlines_save input[name="customer_id"]').val(customer_id)
            }
        }
    });

    return false;
})

$('form#form_box_headlines_save').submit(function (e) {
    "use strict";
    e.preventDefault();
    let customer_id = $('form#form_box_headlines_save select[name="customer_id"]').val()

    $('#save_box_headline_button').prop('disabled', true);
    $('#save_box_headline_button').text('Aguarde salvando...');

    var formData = new FormData(this);

    // Cria o FormData a partir de outro formulário
    var formDataHeadlineBoxSelected = new FormData(document.getElementById('box-headlines-save'));

    // Adiciona os dados do segundo formulário ao primeiro
    for (var pair of formDataHeadlineBoxSelected.entries()) {
        formData.append(pair[0], pair[1]);
    }

    $.ajax({
        type: 'post',
        url: 'dashboard/box-headlines/customer/'+customer_id+'/save',
        data: formData,
        dataType: 'json',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

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
            if(data.button){
                $('#save_box_headline_button').prop('disabled', false);
                $('#save_box_headline_button').html('[SVG]\n'+
                    '                            Salvar');
            }
            if(data.reset){
                $('#form_box_headlines_save')[0].reset();
                $('#box-headlines-select-customers')[0].tomselect.clear();
                $("form#form_box_headlines_save select[name='headline_week_id']").html('<option value="">Selecione um cliente primeiro.</option>')
            }
            if(data.modalOut){
                $('#modal-box-headlines-save').modal('hide');
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
                toastr.error('Ocorreu um erro ao salvar as Headline.');
            }

            $('#save_box_headline_button').prop('disabled', false);
            $('#save_box_headline_button').html('[SVG]\n'+
                '                            Salvar');
        }
    });

    return false;
})

$('.j_box_remove_headlines').on('click', function(){
    // Cria o FormData a partir de outro formulário
    var formData = new FormData(document.getElementById('box-headlines-save'));

    $.ajax({
        type: 'post',
        url: 'dashboard/box-headlines/remove',
        data: formData,
        dataType: 'json',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.success){
                $('.j_box-headlines-list').html(data.box_headlines)
            }
            if(data.fade_out){
                $('.j_headline_icon_box').fadeOut();
                $('#offcanvasEnd').offcanvas('hide');
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
                toastr.error('Ocorreu um erro ao salvar as Headline.');
            }

            $('#save_box_headline_button').prop('disabled', false);
            $('#save_box_headline_button').html('[SVG]\n'+
                '                            Salvar');
        }
    });

    return false;
})

var clickedButtonFormBox = '';

// Captura o ID do botão clicado antes do envio do formulário
// $('form#box-headlines-save button').on('click', function () {
//     clickedButtonFormBox = $(this).attr('id');
// });
// $('form#box-headlines-save').submit(function (e) {
//     "use strict";
//     e.preventDefault();
//
//     $('#make_headlines_button').prop('disabled', true);
//     $('#make_headlines_button').text('Aguarde salvando...');
//
//     var formData = new FormData(this);
//
//     var routeSend;
//
//     if(clickedButtonFormBox == 'box_save_headlines'){
//         routeSend = 'dashboard/';
//     }else if(clickedButtonFormBox == 'box_make_roadmap'){
//         routeSend = '';
//     }
//
//     $.ajax({
//         type: "post",
//         url: "/dashboard/box-headlines/make",
//         data: formData,
//         // dataType: 'JSON',
//         contentType: false,
//         processData: false,
//         success: function(data){
//             toastr[data.type](data.message);
//
//             if(data.redirect){
//                 setTimeout(function(){
//                     location.href = data.redirect;
//                 }, 1000);
//             }
//             if(data.refresh){
//                 setTimeout(function(){
//                     window.location.reload();
//                 }, 1000);
//             }
//             if(data.button){
//                 $('#make_headlines_button').prop('disabled', false);
//                 $('#make_headlines_button').html('[SVG]\n'+
//                     '                            Gerar Headlines');
//             }
//             if(data.reset){
//                 $('#make-headlines')[0].reset();
//                 $('#make-headlines-select-customers')[0].tomselect.clear();
//                 $('#make-headlines-select-structures')[0].tomselect.clear();
//                 $('#make-headlines-select-variables')[0].tomselect.clear();
//                 $('.j_all_values').fadeOut(300);
//             }
//             if(data.modalOut){
//                 $('#modal-make-headlines').modal('hide');
//             }
//
//         },
//         error: function(data) {
//             if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
//                 var errors = data.responseJSON.errors;
//                 $.each(errors, function(index, value) {
//                     toastr.error(value);
//                     console.error(value);
//                 });
//             } else {
//                 toastr.error('Ocorreu um erro ao gerar a Headline.');
//             }
//
//             $('#make_headlines_button').prop('disabled', false);
//             $('#make_headlines_button').html('[SVG]\n'+
//                 '                            Gerar Headlines');
//         }
//     });
//     return false;
// });
