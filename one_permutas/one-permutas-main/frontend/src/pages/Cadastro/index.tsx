import FormCadastro from '../../forms/Cadastro'

import { FormContainer } from './styles'

import logo from '../../assets/Logo-one.png'

const Cadastro = () => {
  return (
    <FormContainer>
      <img src={logo} alt="" />
      <FormCadastro />
    </FormContainer>
  )
}

export default Cadastro
