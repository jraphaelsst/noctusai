import FormCadastro from '../../forms/Cadastro'
import {
  FormContainer,
  LogoSection,
  FormSection,
  FormCard,
  FormTitle,
  FormSubtitle
} from '../Login/styles'
import logo from '../../assets/Logo-one.png'

const Cadastro = () => {
  return (
    <FormContainer>
      <LogoSection>
        <img src={logo} alt="Sistema de Permutas" />
      </LogoSection>
      <FormSection>
        <FormCard>
          <FormTitle>Criar Conta</FormTitle>
          <FormSubtitle>Preencha os dados para se cadastrar</FormSubtitle>
          <FormCadastro />
        </FormCard>
      </FormSection>
    </FormContainer>
  )
}

export default Cadastro
