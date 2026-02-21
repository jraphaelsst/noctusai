import FormLogin from '../../forms/Login'

import { FormContainer } from './styles'

import logo from '../../assets/Logo-one.png'

const Login = () => {
  return (
    <FormContainer>
      <img src={logo} alt="" />
      <FormLogin />
    </FormContainer>
  )
}

export default Login
