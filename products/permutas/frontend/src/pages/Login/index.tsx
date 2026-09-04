import FormLogin from '../../forms/Login'
import {
  FormContainer,
  LogoSection,
  FormSection,
  FormCard,
  FormTitle,
  FormSubtitle
} from './styles'
import logo from '../../assets/Logo-one.png'

const Login = () => {
  return (
    <FormContainer>
      <LogoSection>
        <img src={logo} alt="Sistema de Permutas" />
      </LogoSection>
      <FormSection>
        <FormCard>
          <FormTitle>Bem-vindo</FormTitle>
          <FormSubtitle>Entre com suas credenciais para acessar</FormSubtitle>
          <FormLogin />
        </FormCard>
      </FormSection>
    </FormContainer>
  )
}

export default Login
