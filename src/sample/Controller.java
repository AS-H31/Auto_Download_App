package sample;

import javafx.event.ActionEvent;
import javafx.fxml.FXML;
import javafx.scene.text.Text;
import javafx.stage.DirectoryChooser;
import javafx.stage.Stage;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.URL;

public class Controller {

    @FXML
    Text result;
    public void showFilechooser(ActionEvent actionEvent){
        DirectoryChooser directoryChooser = new DirectoryChooser();

        File selectedDirectory = directoryChooser.showDialog(new Stage());
        String path = selectedDirectory.getAbsolutePath() + "\\output.zip";

        System.out.println(path);

        // TODO:
       result.setText("Datei wurde in " + path + " gespeichert");

        try {
            URL gitHubLink = new URL("https://github.com/ahmadShiyarHesso/ComplitionProgress-ueberarbeitet/archive/main.zip");
            /* openStream() Opens connection with the URL and gives an input stream which is used to read
            data from the connection */
            BufferedInputStream inputStream = new BufferedInputStream(gitHubLink.openStream());
            FileOutputStream fos = new FileOutputStream(path);

            /*
            The contents are read as bytes and copied
            to a file in the local directory using the FileOutputStream
             */

            byte data[] = new byte[1024];
            int byteContent;

            while ((byteContent= inputStream.read(data, 0, 1024)) != -1){
                fos.write(data, 0, byteContent);
            }
        }catch (IOException e){
            System.out.println("fehler");
        }

    }

}
