import { useEffect, useState } from 'react'

import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../../utils/useAxios'

import Container from '../../../containers/Container'
import DropDown from '../../../components/DropDown'
import DropDownContainer from '../../../containers/DropDownContainer'

import { Form, FormField, FormInput, FormLabel } from './styles'
import Button from '../../../components/Button'

declare module 'jwt-decode' {
  export interface JwtPayload {
    user_id: string
  }
}

const NovoCliente = () => {
  const baseUrl = ''
  const api = useAxios()

  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const [proprietarioActive, setProprietarioActive] = useState(false)
  const [nomeProprietario, setNomeProprietario] = useState('')
  const [corretor, setCorretor] = useState('')
  const [telefoneProprietario, setTelefoneProprietario] = useState('')
  const [emailProprietario, setEmailProprietario] = useState('')

  useEffect(() => {
    const propDropDownEl = document.getElementById('proprietario-dropdown')
    const propForm = document.getElementById('proprietario-form')
    const propInputFields = document.getElementsByClassName(
      'proprietario-input-field'
    )

    const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
      el?.classList.add('active')
      for (let i = 0; i < els.length; i++) {
        els[i].classList.add('activeInput')
      }
    }

    const handleClick = () => {
      setProprietarioActive(!proprietarioActive)
      proprietarioActive
        ? addClass(propForm!, propInputFields)
        : propForm?.classList.remove('active')
    }
    propDropDownEl?.addEventListener('click', handleClick)
    return () => {
      propDropDownEl?.removeEventListener('click', handleClick)
    }
  }, [proprietarioActive])

  // Cadastrar Proprietário
  useEffect(() => {
    const botaoCadastrar = document.getElementById(
      'botao-cadastrar-proprietario'
    )
    const handleSubmit = () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('nome', nomeProprietario)
      formdata.append('corretor', corretor)
      formdata.append('telefone', telefoneProprietario)
      formdata.append('email', emailProprietario)

      try {
        const cadastrarProprietario = async () => {
          const response = await api.post(baseUrl + '/proprietario/', formdata)
          if (response.status === 201) {
            swal.fire({
              title: 'Proprietário cadastrado com sucesso!',
              icon: 'success',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          }
          setNomeProprietario('')
          setCorretor('')
          setTelefoneProprietario('')
          setEmailProprietario('')
        }
        cadastrarProprietario()
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
    nomeProprietario,
    corretor,
    telefoneProprietario,
    emailProprietario
  ])

  return (
    <Container title="Novo Proprietário">
      <DropDownContainer>
        <div>
          <DropDown id="proprietario-dropdown" title="Proprietário" />
          <Form id="proprietario-form" className="">
            <FormField className="proprietario-input-field">
              <FormLabel>Corretor:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setCorretor(e.target.value)
                }}
                value={corretor}
                type="text"
              />
            </FormField>
            <FormField className="proprietario-input-field">
              <FormLabel>Nome:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setNomeProprietario(e.target.value)
                }}
                value={nomeProprietario}
                type="text"
              />
            </FormField>
            <FormField className="proprietario-input-field">
              <FormLabel>Telefone:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setTelefoneProprietario(e.target.value)
                }}
                value={telefoneProprietario}
                type="text"
              />
            </FormField>
            <FormField className="proprietario-input-field">
              <FormLabel>Email:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setEmailProprietario(e.target.value)
                }}
                value={emailProprietario}
                type="email"
              />
            </FormField>
          </Form>
        </div>
        <Button id="botao-cadastrar-proprietario" type="button">
          Cadastrar
        </Button>
      </DropDownContainer>
    </Container>
  )
}

export default NovoCliente
