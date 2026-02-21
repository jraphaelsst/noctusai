import { useEffect, useState } from 'react'

import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../../utils/useAxios'

import Container from '../../../containers/Container'
import DropDownContainer from '../../../containers/DropDownContainer'
import DropDown from '../../../components/DropDown'
import Button from '../../../components/Button'

import { Form, FormField, FormInput, FormLabel } from './styles'

declare module 'jwt-decode' {
  export interface JwtPayload {
    user_id: string
  }
}

const NovoCondominio = () => {
  const baseUrl = 'http://localhost:8000'
  const api = useAxios()

  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const [condominioActive, setCondominioActive] = useState(false)
  const [nomeCondominio, setNomeCondominio] = useState('')
  const [numero, setNumero] = useState('')
  const [km, setKm] = useState('')
  const [valor, setValor] = useState('')

  const [cep, setCep] = useState('')
  const [estado, setEstado] = useState('')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [rua, setRua] = useState('')

  useEffect(() => {
    const condominioDropDownEl = document.getElementById('condominio-dropdown')
    const condominioForm = document.getElementById('condominio-form')
    const condominioInputFields = document.getElementsByClassName(
      'condominio-input-field'
    )

    const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
      el?.classList.add('active')
      for (let i = 0; i < els.length; i++) {
        els[i].classList.add('activeInput')
      }
    }

    const handleClick = () => {
      setCondominioActive(!condominioActive)
      condominioActive
        ? addClass(condominioForm!, condominioInputFields)
        : condominioForm?.classList.remove('active')
    }

    condominioDropDownEl?.addEventListener('click', handleClick)
    return () => {
      condominioDropDownEl?.removeEventListener('click', handleClick)
    }
  }, [condominioActive])

  // Consulta CEP
  const consultaCep = () => {
    const limpa_formulario_cep = () => {
      // Rua
      setRua('')
      // Bairro
      setBairro('')
      // Cidade
      setCidade('')
      // Estado
      setEstado('')
    }
    // Checa se o valor de CEP não é nulo
    if (cep != '') {
      // Testa a formatação do CEP
      const validacep = /^[0-9]{8}$/
      if (validacep.test(cep)) {
        // Preenche os valores dos campos com "..." enquanto aguarda resposta da API
        // Rua
        setRua('...')
        // Bairro
        setBairro('...')
        // Cidade
        setCidade('...')
        // Estado
        setEstado('...')

        // Consulta o webservice viacep.com.br
        const fetchCep = async (cep: string) => {
          await fetch('https://viacep.com.br/ws/' + cep + '/json/?callback=', {
            method: 'GET'
          }).then((response: Response) => {
            if (!('erro' in response)) {
              response.json().then((data) => {
                setRua(data.logradouro)
                setBairro(data.bairro)
                setCidade(data.localidade)
                setEstado(data.uf)
              })
            } else {
              limpa_formulario_cep()
              alert('CEP não encontrado.')
            }
          })
        }
        fetchCep(cep)
      } else {
        limpa_formulario_cep()
        alert('Formato de CEP inválido.')
      }
    } else {
      limpa_formulario_cep()
    }
  }

  useEffect(() => {
    const botaoCadastrar = document.getElementById('botao-cadastrar-condominio')
    const handleSubmit = async () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('nome', nomeCondominio)
      formdata.append('cep', cep)
      formdata.append('estado', estado)
      formdata.append('cidade', cidade)
      formdata.append('bairro', bairro)
      formdata.append('endereco', rua)
      formdata.append('numero', numero)
      formdata.append('km', km)
      formdata.append('valor_condominio', valor)

      try {
        const cadastrarCondominio = async () => {
          const response = await api.post(baseUrl + '/condominio/', formdata)
          if (response.status === 201) {
            swal.fire({
              title: 'Condomínio criado com sucesso!',
              icon: 'success',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          } else {
            swal.fire({
              title: 'Houve algum erro, verifique os dados.',
              icon: 'error',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          }
          setNomeCondominio('')
          setCep('')
          setEstado('')
          setCidade('')
          setBairro('')
          setRua('')
          setNumero('')
          setKm('')
          setValor('')
        }
        cadastrarCondominio()
      } catch (error) {
        console.log(error)
      }
    }

    if (botaoCadastrar) {
      botaoCadastrar.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrar) {
        botaoCadastrar.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    api,
    user_id,
    nomeCondominio,
    cep,
    estado,
    cidade,
    bairro,
    rua,
    numero,
    km,
    valor
  ])

  return (
    <Container title="Novo Condomínio">
      <DropDownContainer>
        <div>
          <DropDown id="condominio-dropdown" title="Condomínio" />
          <Form id="condominio-form" className="">
            <FormField className="condominio-input-field">
              <FormLabel>Nome:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setNomeCondominio(e.target.value)
                }}
                value={nomeCondominio}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Cep:</FormLabel>
              <FormInput
                type="text"
                onChange={(e) => {
                  setCep(e.target.value)
                }}
                onBlur={consultaCep}
                value={cep}
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Estado:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setEstado(e.target.value)
                }}
                value={estado}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Cidade:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setCidade(e.target.value)
                }}
                value={cidade}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Bairro:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setBairro(e.target.value)
                }}
                value={bairro}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Endereço:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setRua(e.target.value)
                }}
                value={rua}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Número:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setNumero(e.target.value)
                }}
                value={numero}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Km Raposo:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setKm(e.target.value)
                }}
                value={km}
                type="text"
              />
            </FormField>
            <FormField className="condominio-input-field">
              <FormLabel>Valor:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setValor(e.target.value)
                }}
                value={valor}
                type="number"
              />
            </FormField>
          </Form>
        </div>
        <Button id="botao-cadastrar-condominio" type="button">
          Cadastrar
        </Button>
      </DropDownContainer>
    </Container>
  )
}

export default NovoCondominio
