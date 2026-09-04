import { ChangeEvent, FormEvent, useContext, useState } from 'react'

import Form from '../../components/Form'
import Input from '../../components/Input'
import Button from '../../components/Button'

import { LinkTo } from './styles'

import AuthContext from '../../context/AuthContext'

const FormLogin = () => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const { loginUser } = useContext(AuthContext)

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    loginUser(email, password)
  }

  return (
    <Form title="Login" onSubmit={handleSubmit}>
      <>
        <Input
          id="emailInput"
          type="email"
          placeholder="Email"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setEmail(e.target.value)
          }}
        />
        <Input
          id="passwordInput"
          type="password"
          placeholder="Senha"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setPassword(e.target.value)
          }}
        />
        <Button type="submit">Login</Button>
        <LinkTo to="">Esqueceu sua senha?</LinkTo>
      </>
    </Form>
  )
}

export default FormLogin
