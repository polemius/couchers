import { CircularProgress, Container } from "@material-ui/core";
import Alert from "components/Alert";
import { useAppRouteStyles } from "components/AppRoute";
import HtmlMeta from "components/HtmlMeta";
import StyledLink from "components/StyledLink";
import { Empty } from "google-protobuf/google/protobuf/empty_pb";
import { Error as GrpcError } from "grpc-web";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useMutation } from "react-query";
import { loginRoute } from "routes";
import { service } from "service";

export default function CompleteResetPassword({
  resetToken,
}: {
  resetToken?: string;
}) {
  const { t } = useTranslation("auth");
  const classes = useAppRouteStyles();

  const {
    error,
    isLoading,
    isSuccess,
    mutate: completePasswordReset,
  } = useMutation<Empty, GrpcError, string>((resetToken) =>
    service.account.completePasswordReset(resetToken)
  );

  useEffect(() => {
    if (resetToken) {
      completePasswordReset(resetToken);
    }
  }, [completePasswordReset, resetToken]);

  return (
    <Container className={classes.standardContainer}>
      <HtmlMeta title={t("reset_password")} />
      {isLoading ? (
        <CircularProgress />
      ) : isSuccess ? (
        <>
          <Alert severity="success">{t("reset_password_success")}</Alert>
          <StyledLink href={loginRoute}>{t("login_prompt")}</StyledLink>
        </>
      ) : error ? (
        <Alert severity="error">
          {t("reset_password_error", { message: error.message })}
        </Alert>
      ) : (
        ""
      )}
    </Container>
  );
}
