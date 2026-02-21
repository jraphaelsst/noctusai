import { ChangeEvent, FormEvent, useContext, useState } from 'react'

import Form from '../../components/Form'
import Input from '../../components/Input'
import Button from '../../components/Button'

import { LinkTo } from './styles'

import AuthContext from '../../context/AuthContext'

const FormCadastro = () => {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')

  const { registerUser } = useContext(AuthContext)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    registerUser(username, email, password, password2)
  }

  return (
    <Form title="Cadastrar" onSubmit={handleSubmit}>
      <>
        <Input
          id="nomeInput"
          type="text"
          placeholder="Nome"
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            setUsername(e.target.value)
          }
        />
        <Input
          id="emailInput"
          type="email"
          placeholder="Email"
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            setEmail(e.target.value)
          }
        />
        <Input
          id="passwordInput"
          type="password"
          placeholder="Senha"
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            setPassword(e.target.value)
          }
        />
        <Input
          id="password2Input"
          type="password"
          placeholder="Confirmar Senha"
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            setPassword2(e.target.value)
          }
        />
        <Button type="submit">Cadastrar</Button>
        <LinkTo to="/login">Possui uma conta?</LinkTo>
      </>
    </Form>
  )
}

export default FormCadastro
